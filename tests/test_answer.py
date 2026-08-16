import json
import threading
import unittest
from unittest.mock import patch
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from types import SimpleNamespace

from kb_pipeline.answer import (AnswerUnavailable, AnswerValidationError, OllamaAnswerer,
                                OpenAIAnswerer, validate_answer_result)
from kb_pipeline.api import create_server
from kb_pipeline.composition import RuntimeConfig, compose
from kb_pipeline.service import KnowledgeService


class CapturingAnswerer:
    provider = "test"
    model = "test-model"

    def __init__(self, result=None):
        self.evidence = None
        self.result = result or {"answer": "supported", "grounded": True, "citations": []}

    def answer(self, query, evidence):
        self.evidence = evidence
        return {**self.result, "provider": self.provider, "model": self.model,
                "citations": [evidence[0].get("citation_id", evidence[0].get("document_id"))] if evidence and self.result.get("grounded") else []}


class AnswerTests(unittest.TestCase):
    def test_openai_request_is_structured_bounded_and_evidence_only(self):
        class Responses:
            def __init__(self): self.kwargs = None
            def create(self, **kwargs):
                self.kwargs = kwargs
                return SimpleNamespace(output_text=json.dumps({"answer": "supported", "grounded": True, "citations": ["E1"]}))
        responses = Responses()
        evidence = ({"citation_id": "E1", "title": "t", "snippet": "s", "provenance": []},)
        answer = OpenAIAnswerer("gpt-test", timeout_seconds=7, max_retries=1,
                                client=SimpleNamespace(responses=responses)).answer("q", evidence)
        self.assertEqual(["E1"], answer["citations"])
        self.assertEqual("gpt-test", responses.kwargs["model"])
        self.assertFalse(responses.kwargs["store"])
        self.assertEqual("json_schema", responses.kwargs["text"]["format"]["type"])
        self.assertIn("<evidence>", responses.kwargs["input"])
        self.assertIn('"citation_id":"E1"', responses.kwargs["input"])
        with self.assertRaises(AnswerValidationError):
            OpenAIAnswerer("gpt-test", client=SimpleNamespace(responses=responses)).answer("q", ({"snippet": "x" * 100000},))

    def test_openai_malformed_and_unsupported_citation_fail_closed(self):
        evidence = ({"citation_id": "E1", "title": "t", "snippet": "s", "provenance": []},)
        for output in ("not-json", json.dumps({"answer": "x", "grounded": True, "citations": ["E2"]})):
            client = SimpleNamespace(responses=SimpleNamespace(create=lambda **_: SimpleNamespace(output_text=output)))
            with self.assertRaises(AnswerValidationError):
                OpenAIAnswerer("gpt-test", client=client).answer("q", evidence)

    def test_openai_provider_failures_are_safe_and_unavailable(self):
        evidence = ({"citation_id": "E1", "title": "t", "snippet": "s", "provenance": []},)
        for error in (TimeoutError("secret"), ConnectionError("secret")):
            client = SimpleNamespace(responses=SimpleNamespace(create=lambda **_: (_ for _ in ()).throw(error)))
            with self.assertRaises(AnswerUnavailable) as raised:
                OpenAIAnswerer("gpt-test", client=client).answer("q", evidence)
            self.assertNotIn("secret", str(raised.exception))
        for status in (401, 429, 500, 503):
            error = type("SDKStatusError", (Exception,), {"status_code": status})("secret")
            def fail(**kwargs):
                raise error
            client = SimpleNamespace(responses=SimpleNamespace(create=fail))
            with self.assertRaises(AnswerUnavailable):
                OpenAIAnswerer("gpt-test", client=client).answer("q", evidence)
    def test_default_answer_is_deterministic_abstention(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            app = compose(RuntimeConfig(root / "db", root))
            answer = app.service.answer("anything", "reader")
            self.assertFalse(answer["grounded"])
            self.assertEqual([], answer["citations"])
            self.assertEqual("deterministic-local", answer["provider"])

    def test_authenticated_api_and_bounded_dto(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "doc.txt").write_text("local answer evidence")
            app = compose(RuntimeConfig(root / "db", root))
            app.service.ingest(next(app.connector.read()), "answer-test")
            server, token = create_server(app.service, port=0)
            thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
            url = f"http://{server.server_address[0]}:{server.server_address[1]}/v1/answer"
            try:
                with self.assertRaises(HTTPError) as unauthenticated:
                    urlopen(Request(url, data=b'{"query":"local"}', method="POST"))
                self.assertEqual(401, unauthenticated.exception.code)
                response = urlopen(Request(url, data=b'{"query":"local"}', method="POST",
                                           headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"}))
                body = json.load(response)
                self.assertEqual("deterministic-local", body["provider"])
                self.assertFalse(body["grounded"])
                self.assertEqual([], body["citations"])
            finally:
                server.shutdown(); server.server_close(); thread.join(timeout=2)

    def test_answer_uses_only_search_acl_results(self):
        answerer = CapturingAnswerer()
        service = object.__new__(KnowledgeService)
        service.answerer = answerer
        service.search = lambda query, identity, is_admin=False: [SimpleNamespace(document_id="allowed", title="safe", snippet="safe", source_version="1")]
        service.store = SimpleNamespace(get=lambda document_id: SimpleNamespace(metadata={}))
        service.search_metadata = lambda hit: {"provenance": [{"kind": "raw", "identifier": "safe-id"}]}
        result = service.answer("untrusted", "reader")
        self.assertEqual("E1", next(iter(answerer.evidence or ())) ["citation_id"])
        self.assertEqual("allowed", result["citations"][0]["document_id"])

    def test_citation_subset_and_abstention_validation(self):
        evidence = ({"document_id": "doc-1", "title": "t", "snippet": "s", "provenance": []},)
        with self.assertRaises(AnswerValidationError):
            validate_answer_result({"answer": "x", "grounded": True, "citations": ["not-supplied"]}, evidence, "p", "m")
        abstained = validate_answer_result({"answer": "ignored", "grounded": False, "citations": ["doc-1"]}, evidence, "p", "m")
        self.assertFalse(abstained["grounded"])
        self.assertEqual([], abstained["citations"])

    def test_ollama_malformed_and_oversized_responses_fail_without_live_network(self):
        class Response:
            def __init__(self, body): self.body = body
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def read(self, limit): return self.body

        evidence = ({"document_id": "doc-1", "title": "t", "snippet": "s", "provenance": []},)
        with patch("kb_pipeline.answer._open_local", return_value=Response(b"not-json")):
            with self.assertRaises(AnswerValidationError):
                OllamaAnswerer().answer("q", evidence)
        with patch("kb_pipeline.answer._open_local", return_value=Response(b"x" * (256 * 1024 + 1))):
            with self.assertRaises(AnswerValidationError):
                OllamaAnswerer().answer("q", evidence)

    def test_ollama_requests_structured_json_and_accepts_valid_response(self):
        class Response:
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def read(self, limit):
                return json.dumps({"response": json.dumps({"answer": "supported", "grounded": True,
                                                             "citations": ["doc-1"]})}).encode()

        evidence = ({"document_id": "doc-1", "title": "t", "snippet": "s", "provenance": []},)
        with patch("kb_pipeline.answer._open_local", return_value=Response()) as request:
            answer = OllamaAnswerer().answer("q", evidence)
        sent = json.loads(request.call_args.args[0].data)
        self.assertEqual("object", sent["format"]["type"])
        self.assertEqual({"answer", "grounded", "citations"}, set(sent["format"]["required"]))
        self.assertIn("untrusted data", sent["prompt"])
        self.assertEqual(["doc-1"], answer["citations"])

    def test_ollama_connectivity_and_invalid_citation_are_distinct(self):
        evidence = ({"document_id": "doc-1", "title": "t", "snippet": "s", "provenance": []},)
        with patch("kb_pipeline.answer._open_local", side_effect=OSError("offline")):
            with self.assertRaises(AnswerUnavailable):
                OllamaAnswerer().answer("q", evidence)
        class Response:
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def read(self, limit):
                return b'{"response":"{\\"answer\\":\\"x\\",\\"grounded\\":true,\\"citations\\":[\\"other\\"]}"}'
        with patch("kb_pipeline.answer._open_local", return_value=Response()):
            with self.assertRaises(AnswerValidationError):
                OllamaAnswerer().answer("q", evidence)

    def test_service_retries_validation_once_with_identical_evidence(self):
        class RetryAnswerer:
            def __init__(self): self.calls = []; self.results = [
                {"answer": "bad", "grounded": True, "citations": ["unknown"]},
                {"answer": "good", "grounded": True, "citations": ["E1"]}]
            def answer(self, query, evidence): self.calls.append(evidence); return self.results.pop(0)
        with TemporaryDirectory() as tmp:
            root = Path(tmp); (root / "doc.txt").write_text("known evidence")
            answerer = RetryAnswerer(); app = compose(RuntimeConfig(root / "db", root, answerer=answerer))
            app.service.ingest(next(item for item in app.connector.read() if item.external_id == "doc.txt"), "answer")
            result = app.service.answer("known", "reader")
            self.assertEqual("good", result["answer"])
            self.assertEqual(2, len(answerer.calls)); self.assertIs(answerer.calls[0], answerer.calls[1])

    def test_abstention_and_unavailable_are_not_retried(self):
        class Abstainer:
            def __init__(self): self.calls = 0
            def answer(self, query, evidence): self.calls += 1; return {"answer": "no", "grounded": False, "citations": []}
        class Offline:
            def __init__(self): self.calls = 0
            def answer(self, query, evidence): self.calls += 1; raise AnswerUnavailable("offline")
        with TemporaryDirectory() as tmp:
            root = Path(tmp); (root / "doc.txt").write_text("known evidence")
            abstainer = Abstainer(); app = compose(RuntimeConfig(root / "a.db", root, answerer=abstainer))
            app.service.ingest(next(item for item in app.connector.read() if item.external_id == "doc.txt"), "answer")
            self.assertFalse(app.service.answer("known", "reader")["grounded"]); self.assertEqual(1, abstainer.calls)
            offline = Offline(); app = compose(RuntimeConfig(root / "b.db", root, answerer=offline))
            app.service.ingest(next(item for item in app.connector.read() if item.external_id == "doc.txt"), "answer")
            with self.assertRaises(AnswerUnavailable): app.service.answer("known", "reader")
            self.assertEqual(1, offline.calls)


if __name__ == "__main__":
    unittest.main()
