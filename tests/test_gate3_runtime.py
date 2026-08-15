import tempfile
import threading
import unittest
import json
from http.cookiejar import CookieJar
from urllib.request import build_opener
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen, HTTPCookieProcessor

from kb_pipeline.api import create_server
from kb_pipeline.composition import RuntimeConfig, compose


class Gate3RuntimeTests(unittest.TestCase):
    def test_search_dto_redacts_uri_and_exposes_provenance_contract(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); (root / "one.txt").write_text("alpha")
            app = compose(RuntimeConfig(root / "db.sqlite", root))
            app.service.ingest(next(item for item in app.connector.read() if item.external_id == "one.txt"), "qa")
            server, token = create_server(app.service, port=0)
            thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
            base = f"http://{server.server_address[0]}:{server.server_address[1]}"
            try:
                response = urlopen(Request(base + "/v1/search?q=alpha", headers={"Authorization": f"Bearer {token}"}))
                body = json.load(response); hit = body["items"][0]
                serialized = json.dumps(body)
                self.assertNotIn(str(root), serialized)
                self.assertNotIn("file://", serialized)
                for field in ("object_key", "source_identity", "source_version", "raw_record_reference",
                              "provenance_reference", "observed_at", "indexed_at", "ledger_sequence",
                              "projection_sequence", "status", "freshness_status"):
                    self.assertIn(field, hit)
                self.assertEqual("unknown", hit["indexed_at"])
                self.assertEqual("complete", hit["status"])
            finally:
                server.shutdown(); server.server_close(); thread.join(timeout=2)

    def test_authenticated_report_has_stable_empty_schema_and_values(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            app = compose(RuntimeConfig(root / "db.sqlite", root))
            server, token = create_server(app.service, port=0)
            thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
            base = f"http://{server.server_address[0]}:{server.server_address[1]}"
            try:
                with self.assertRaises(HTTPError) as missing:
                    urlopen(base + "/v1/report")
                self.assertEqual(401, missing.exception.code)
                response = urlopen(Request(base + "/v1/report", headers={"Authorization": f"Bearer {token}"}))
                report = json.load(response)
                self.assertEqual({"documents": 0, "tombstones": 0, "raw_records": 0}, report["counts"])
                self.assertEqual({"sequence": 0, "outbox_pending": 0, "outbox_failed": 0,
                                  "dead_letters": 0, "gaps": 0,
                                  "checkpoints": {"default:state": 0, "default:document": 0,
                                                   "default:lexical": 0, "default:search": 0}}, report["ledger"])
                self.assertEqual("ready", report["readiness"]["status"])
                self.assertTrue(report["projection"]["lag"])
                self.assertTrue(all(value == 0 for value in report["projection"]["lag"].values()))
            finally:
                server.shutdown(); server.server_close(); thread.join(timeout=2)
    def test_clean_start_serves_ui_and_separates_health_readiness(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "one.txt").write_text("alpha")
            app = compose(RuntimeConfig(root / "db.sqlite", root))
            server, token = create_server(app.service, port=0, frontend_root=Path(__file__).parents[1] / "frontend")
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            base = f"http://{server.server_address[0]}:{server.server_address[1]}"
            try:
                self.assertEqual(200, urlopen(base + "/v1/health").status)
                self.assertEqual(200, urlopen(base + "/v1/ready").status)
                self.assertEqual(200, urlopen(base + "/").status)
                request = Request(base + "/v1/search?q=alpha", headers={"Authorization": f"Bearer {token}"})
                self.assertEqual(200, urlopen(request).status)
                with self.assertRaises(HTTPError) as missing:
                    urlopen(base + "/v1/search/alpha")
                self.assertEqual(401, missing.exception.code)
            finally:
                server.shutdown(); server.server_close(); thread.join(timeout=2)

    def test_ui_bootstrap_cookie_authenticates_exact_api_routes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "one.txt").write_text("alpha")
            app = compose(RuntimeConfig(root / "db.sqlite", root))
            server, _ = create_server(app.service, port=0, frontend_root=Path(__file__).parents[1] / "frontend")
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            base = f"http://{server.server_address[0]}:{server.server_address[1]}"
            opener = build_opener(HTTPCookieProcessor(CookieJar()))
            try:
                bootstrap = opener.open(base + "/")
                self.assertIn("HttpOnly", bootstrap.headers["Set-Cookie"])
                self.assertEqual(200, opener.open(base + "/v1/status").status)
                self.assertEqual(200, opener.open(base + "/v1/search?q=alpha").status)
            finally:
                server.shutdown(); server.server_close(); thread.join(timeout=2)

    def test_api_state_is_per_server(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "one.txt").write_text("alpha")
            first = compose(RuntimeConfig(root / "one.db", root))
            second = compose(RuntimeConfig(root / "two.db", root))
            left, left_token = create_server(first.service, port=0)
            right, right_token = create_server(second.service, port=0)
            left_thread = threading.Thread(target=left.serve_forever, daemon=True)
            right_thread = threading.Thread(target=right.serve_forever, daemon=True)
            left_thread.start(); right_thread.start()
            try:
                left_url = f"http://{left.server_address[0]}:{left.server_address[1]}/v1/status"
                right_url = f"http://{right.server_address[0]}:{right.server_address[1]}/v1/status"
                self.assertEqual(200, urlopen(Request(left_url, headers={"Authorization": f"Bearer {left_token}"})).status)
                with self.assertRaises(HTTPError) as wrong:
                    urlopen(Request(right_url, headers={"Authorization": f"Bearer {left_token}"}))
                self.assertEqual(401, wrong.exception.code)
            finally:
                left.shutdown(); right.shutdown(); left.server_close(); right.server_close()
                left_thread.join(timeout=2); right_thread.join(timeout=2)

    def test_production_rejects_test_crypto(self):
        with tempfile.TemporaryDirectory() as tmp:
            from kb_pipeline.protocol import LocalTestKeyProvider
            root = Path(tmp)
            with self.assertRaises(ValueError):
                RuntimeConfig(root / "db", root, mode="production", payload_provider=LocalTestKeyProvider()).validate()

    def test_document_lag_100_is_not_ready_and_watermarks_are_exact(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); source = root / "source"; source.mkdir()
            app = compose(RuntimeConfig(root / "db.sqlite", source))
            for number in range(100):
                (source / f"{number}.txt").write_text(f"synthetic-{number}")
            for item in app.connector.read():
                app.service.ingest(item, "lag-test")
            with app.store.writer_lock:
                app.service.ledger.db.execute("UPDATE protocol_checkpoints SET sequence=0 WHERE stream='default:state'")
                app.service.ledger.db.commit()
            health = app.service.health()
            self.assertEqual(100, health["ledger_sequence"])
            self.assertEqual(0, health["watermarks"]["document"])
            self.assertEqual(100, health["projection_lag"]["default:document"])
            self.assertEqual("not_ready", app.service.readiness()["status"])

    def test_sqlite_threaded_readers_and_single_writer_have_bounded_outcomes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); source = root / "source"; source.mkdir()
            app = compose(RuntimeConfig(root / "db.sqlite", source))
            errors = []; reads = []; lock = threading.Lock()
            def reader():
                try:
                    for _ in range(100):
                        app.store.status(); app.store.all(); reads.append(1)
                except Exception as exc:
                    with lock: errors.append(type(exc).__name__)
            def writer():
                try:
                    for item in app.connector.read(): app.service.ingest(item, "concurrent")
                except Exception as exc:
                    with lock: errors.append(type(exc).__name__)
            threads = [threading.Thread(target=reader) for _ in range(6)] + [threading.Thread(target=writer)]
            for thread in threads: thread.start()
            for thread in threads: thread.join(timeout=30)
            self.assertTrue(all(not thread.is_alive() for thread in threads))
            self.assertEqual([], errors)
            self.assertGreater(len(reads), 0)
            self.assertLessEqual(app.store.status()["busy_timeout_ms"], 30000)


if __name__ == "__main__":
    unittest.main()
