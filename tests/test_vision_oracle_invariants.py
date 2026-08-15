import unittest
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory

from kb_pipeline.adapters import ContentAwareCanonicalizer, LocalFilesConnector
from kb_pipeline.answer import OllamaAnswerer
from kb_pipeline.composition import RuntimeConfig, compose
from kb_pipeline.security import FakeKMSProvider
from kb_pipeline.vision import LocalOllamaVisionObserver


def jpeg(width=3, height=2):
    return b"\xff\xd8\xff\xc0\x00\x0b\x08" + height.to_bytes(2, "big") + width.to_bytes(2, "big") + b"\x01\x01\x11\x00\xff\xd9"


class VisualObserver:
    model = "fake"
    def observe(self, payload, filename):
        return {"visible_text": ["VISUAL"], "orientation": "landscape", "markers_devices": [],
                "image_quality": "clear", "summary": "A local image.", "uncertainty": [],
                "label_candidates": {"modality": [{"candidate": "photograph", "source": "model_observation"}],
                                     "body_region": [], "projection_view": [], "subject_species": []}}


class VisionOracleInvariantTests(unittest.TestCase):
    def test_malformed_jpeg_is_rejected_before_classification(self):
        with TemporaryDirectory() as directory:
            root = Path(directory); (root / "bad.jpg").write_bytes(b"\xff\xd8\xffnot-a-jpeg")
            self.assertEqual([], list(LocalFilesConnector(root).read()))
        with self.assertRaises(ValueError):
            ContentAwareCanonicalizer().canonicalize(
                __import__("kb_pipeline.domain", fromlist=["RawRecord"]).RawRecord(
                    __import__("kb_pipeline.domain", fromlist=["SourceVersion"]).SourceVersion("x", "v", "file:///bad.jpg", datetime.now(timezone.utc), "v"),
                    b"\xff\xd8\xffnot-a-jpeg", {}),
                __import__("kb_pipeline.domain", fromlist=["ACL"]).ACL(frozenset({"reader"})))

    def test_artifact_hash_purge_and_payload_provider_wiring(self):
        with TemporaryDirectory() as directory:
            root = Path(directory); source = root / "source"; source.mkdir(); (source / "photo.jpg").write_bytes(jpeg())
            app = compose(RuntimeConfig(root / "db", source, vision_observer=VisualObserver(), payload_provider=FakeKMSProvider(b"key")))
            item = next(app.connector.read()); app.service.ingest(item, "index")
            self.assertIs(app.store.payload_provider, app.config.payload_provider)
            app.store.validate_artifact_links()
            artifact = Path(app.store.db.execute("SELECT artifact FROM raw_records").fetchone()[0])
            artifact.write_bytes(b"tampered")
            with self.assertRaises(ValueError): app.store.validate_artifact_links()
            # Restore valid artifact before transactional purge assertion.
            artifact.write_bytes(item.payload)
            app.service.tombstone("photo.jpg", "reader")
            app.service.purge(datetime.now(timezone.utc), document_id="photo.jpg")
            self.assertIsNone(app.store.image_extraction("photo.jpg", item.metadata["content_hash"]))

    def test_visual_evidence_returns_bounded_server_summary_without_model(self):
        class ExplodingAnswerer:
            def answer(self, query, evidence): raise AssertionError("generic model must not run")
        with TemporaryDirectory() as directory:
            root = Path(directory); source = root / "source"; source.mkdir(); (source / "photo.jpg").write_bytes(jpeg())
            app = compose(RuntimeConfig(root / "db", source, vision_observer=VisualObserver(), answerer=ExplodingAnswerer()))
            app.service.ingest(next(app.connector.read()), "index")
            result = app.service.answer("visual", "reader", max_evidence=1)
            self.assertTrue(result["grounded"])
            self.assertTrue(result["visual_evidence"])
            self.assertEqual(1, result["summary"]["document_count"])
            self.assertEqual("automated visual observation", result["citations"][0]["label"])
            self.assertEqual("success", result["citations"][0]["extraction_status"])
            self.assertTrue(result["citations"][0]["provenance"])
            self.assertEqual("deterministic-local", result["provider"])

    def test_configured_answerer_receives_visual_and_text_evidence(self):
        class CapturingAnswerer:
            model = "fake-answer"
            provider = "fake"
            def __init__(self): self.evidence = None
            def answer(self, query, evidence):
                self.evidence = evidence
                return {"answer": "Evidence-supported answer", "grounded": True,
                        "citations": [item["citation_id"] for item in evidence],
                        "model": self.model, "provider": self.provider}
        with TemporaryDirectory() as directory:
            root = Path(directory); source = root / "source"; source.mkdir()
            (source / "photo.jpg").write_bytes(jpeg()); (source / "note.txt").write_text("local image context")
            answerer = CapturingAnswerer()
            app = compose(RuntimeConfig(root / "db", source, vision_observer=VisualObserver(), answerer=answerer))
            for item in app.connector.read(): app.service.ingest(item, "index")
            result = app.service.answer("local", "reader")
            self.assertTrue(result["grounded"])
            self.assertEqual(2, len(result["citations"]))
            visual = next(item for item in (answerer.evidence or ()) if item.get("visual_evidence"))
            self.assertTrue(visual["non_clinical"])
            self.assertEqual("model_observation", visual["visual_observation"]["label_candidates"]["modality"][0]["source"])

    def test_validation_failure_retries_once_then_visual_fallback(self):
        class Malformed:
            def __init__(self): self.calls = 0
            def answer(self, query, evidence): self.calls += 1; return {}
        with TemporaryDirectory() as directory:
            root = Path(directory); source = root / "source"; source.mkdir(); (source / "photo.jpg").write_bytes(jpeg())
            answerer = Malformed()
            app = compose(RuntimeConfig(root / "db", source, vision_observer=VisualObserver(), answerer=answerer))
            app.service.ingest(next(app.connector.read()), "index")
            result = app.service.answer("visual", "reader")
            self.assertTrue(result["visual_evidence"]); self.assertEqual(2, answerer.calls)

    def test_no_visual_evidence_remains_abstention(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            app = compose(RuntimeConfig(root / "db", root))
            result = app.service.answer("nothing", "reader")
            self.assertFalse(result["grounded"])
            self.assertEqual([], result["citations"])

    def test_visual_summary_uses_acl_filtered_matches(self):
        with TemporaryDirectory() as directory:
            root = Path(directory); source = root / "source"; source.mkdir(); (source / "photo.jpg").write_bytes(jpeg())
            app = compose(RuntimeConfig(root / "db", source, vision_observer=VisualObserver()))
            app.service.ingest(next(app.connector.read()), "index")
            with app.store.writer_lock:
                app.store.db.execute("UPDATE documents SET readers=? WHERE document_id=?", ("[]", "photo.jpg"))
                app.store.db.commit()
            result = app.service.answer("visual", "reader")
            self.assertNotIn("visual_evidence", result)
            self.assertEqual([], result["citations"])

    def test_only_literal_loopback_ip_is_accepted(self):
        for factory in (LocalOllamaVisionObserver, OllamaAnswerer):
            with self.assertRaises(ValueError): factory(endpoint="http://localhost:11434/api/chat", model="local")
            with self.assertRaises(ValueError): factory(endpoint="http://example.test:11434/api/chat", model="local")


if __name__ == "__main__": unittest.main()
