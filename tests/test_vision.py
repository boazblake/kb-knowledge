import base64
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from kb_pipeline.cli import _vision_from_args
from kb_pipeline.composition import RuntimeConfig, compose
from kb_pipeline.vision import LocalOllamaVisionObserver, VisionValidationError, observation_text


def jpeg(width=3, height=2):
    return b"\xff\xd8\xff\xc0\x00\x0b\x08" + height.to_bytes(2, "big") + width.to_bytes(2, "big") + b"\x01\x01\x11\x00\xff\xd9"


OBSERVATION = {"visible_text": ["HELLO"], "orientation": "landscape", "markers_devices": ["screen"],
               "image_quality": "clear", "summary": "A simple local image.", "uncertainty": ["small image"],
               "label_candidates": {"modality": [{"candidate": "photograph", "source": "model_observation"}],
                                    "body_region": [], "projection_view": [], "subject_species": []}}


class Response:
    def __init__(self, body): self.body = body
    def __enter__(self): return self
    def __exit__(self, *args): pass
    def read(self, limit): return self.body


class VisionTests(unittest.TestCase):
    def test_ollama_chat_request_is_bounded_structured_and_loopback(self):
        body = json.dumps({"message": {"content": json.dumps(OBSERVATION)}}).encode()
        with patch("kb_pipeline.vision._open_local", return_value=Response(body)) as call:
            result = LocalOllamaVisionObserver(model="gemma4:local").observe(jpeg(), "photo.jpg")
        request = call.call_args.args[0]
        sent = json.loads(request.data)
        self.assertTrue(request.full_url.endswith("/api/chat"))
        self.assertFalse(sent["stream"])
        self.assertEqual("gemma4:local", sent["model"])
        self.assertEqual(base64.b64encode(jpeg()).decode(), sent["messages"][0]["images"][0])
        self.assertEqual("object", sent["format"]["type"])
        self.assertEqual(OBSERVATION, result)

    def test_invalid_or_oversized_observation_is_rejected_without_live_ollama(self):
        bad = dict(OBSERVATION); bad["unexpected"] = "field"
        body = json.dumps({"message": {"content": json.dumps(bad)}}).encode()
        with patch("kb_pipeline.vision._open_local", return_value=Response(body)):
            with self.assertRaises(VisionValidationError):
                LocalOllamaVisionObserver(model="gemma4:local").observe(jpeg())
        with self.assertRaises(VisionValidationError):
            LocalOllamaVisionObserver(model="gemma4:local").observe(jpeg() + b"x" * (10 * 1024 * 1024))

    def test_cli_activation_and_default_are_explicit(self):
        self.assertIsNone(_vision_from_args("index"))
        observer = _vision_from_args("index", "gemma4:local", "http://127.0.0.1:11434/api/chat", 2)
        assert observer is not None
        self.assertEqual("gemma4:local", observer.model)
        reextract = _vision_from_args("vision-reextract", "gemma4:local")
        assert reextract is not None
        self.assertEqual("gemma4:local", reextract.model)
        with self.assertRaises(ValueError): _vision_from_args("serve", "gemma4:local")
        with self.assertRaises(ValueError): _vision_from_args("index", "gemma4:local", "http://example.test/api/chat")

    def test_service_persists_success_failure_and_identical_no_rerun(self):
        class FakeObserver:
            model = "fake"
            def __init__(self): self.calls = 0
            def observe(self, payload, filename):
                self.calls += 1
                return OBSERVATION
        with TemporaryDirectory() as directory:
            root = Path(directory); source = root / "source"; source.mkdir(); path = source / "photo.jpg"
            path.write_bytes(jpeg())
            observer = FakeObserver()
            app = compose(RuntimeConfig(root / "db", source, vision_observer=observer))
            item = next(app.connector.read())
            self.assertTrue(app.service.ingest(item, "index"))
            self.assertEqual(1, observer.calls)
            document = app.store.get("photo.jpg")
            assert document is not None
            self.assertIn("Visible text: HELLO", document.text)
            extraction = app.store.image_extraction("photo.jpg", item.metadata["content_hash"])
            assert extraction is not None
            self.assertEqual("success", extraction["status"])
            self.assertFalse(app.service.ingest(item, "different-job"))
            self.assertEqual(1, observer.calls)
            path.write_bytes(jpeg(width=4))
            changed = next(app.connector.read())
            self.assertTrue(app.service.ingest(changed, "index"))
            self.assertEqual(2, observer.calls)

    def test_explicit_reextract_updates_labels_fts_and_invalidates_semantics(self):
        class OldObserver:
            model = "old-model"
            def observe(self, payload, filename): return OBSERVATION
        class NewObserver:
            model = "new-model"
            def __init__(self): self.calls = 0
            def observe(self, payload, filename):
                self.calls += 1
                result = dict(OBSERVATION)
                result["label_candidates"] = {**OBSERVATION["label_candidates"],
                    "modality": [{"candidate": "scan", "source": "model_observation"}]}
                return result
        with TemporaryDirectory() as tmp:
            root = Path(tmp); source = root / "source"; source.mkdir()
            (source / "photo.jpg").write_bytes(b"\xff\xd8\xff\xc0\x00\x0b\x08\x00\x02\x00\x03\x01\x01\x11\x00\xff\xd9")
            app = compose(RuntimeConfig(root / "db", source, vision_observer=OldObserver()))
            app.service.ingest(next(app.connector.read()), "index")
            doc = app.store.get("photo.jpg")
            assert doc is not None
            app.store.save_embedding(doc, "fake", (1.0, 0.0), __import__("kb_pipeline.embedding", fromlist=["input_hash"]).input_hash(doc.title, doc.text))
            observer = NewObserver()
            result = app.service.reextract_images(observer)
            self.assertEqual(1, result["processed"]); self.assertEqual(1, observer.calls)
            self.assertTrue(app.service.search("scan", "reader"))
            self.assertEqual(0, len(app.store.embedding_rows("fake")))
            second = app.service.reextract_images(observer)
            self.assertEqual(0, second["processed"]); self.assertEqual(1, second["skipped"])


if __name__ == "__main__": unittest.main()
