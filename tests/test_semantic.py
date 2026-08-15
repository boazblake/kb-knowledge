import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from kb_pipeline.composition import RuntimeConfig, compose
from kb_pipeline.embedding import EmbeddingValidationError, OllamaEmbedder, input_hash
from kb_pipeline.cli import _semantic_reindex


class FakeEmbedder:
    model = "fake-semantic"
    def __init__(self): self.calls = 0
    def embed(self, texts):
        self.calls += 1
        return tuple((1.0, 0.0) if "needle" in text.lower() else (0.0, 1.0) for text in texts)


class SemanticTests(unittest.TestCase):
    def test_semantic_only_hybrid_result_and_no_default_provider(self):
        with TemporaryDirectory() as directory:
            root = Path(directory); source = root / "source"; source.mkdir()
            (source / "one.txt").write_text("unrelated text")
            (source / "two.txt").write_text("other text")
            app = compose(RuntimeConfig(root / "db", source))
            self.assertIsNone(app.service.semantic_embedder)
            for item in app.connector.read(): app.service.ingest(item, "index")
            fake = FakeEmbedder()
            app = compose(RuntimeConfig(root / "db", source, semantic_embedder=fake))
            for doc in app.store.all(): app.store.save_embedding(doc, fake.model, (1.0, 0.0), input_hash(doc.title, doc.text))
            # Query has no lexical match; durable semantic row supplies result.
            self.assertTrue(app.service.search("needle", "reader"))
            self.assertGreater(fake.calls, 0)
            restarted = compose(RuntimeConfig(root / "db", source, semantic_embedder=FakeEmbedder()))
            self.assertTrue(restarted.service.search("needle", "reader"))

    def test_acl_revoke_tombstone_and_revision_invalidate_semantic_rows(self):
        with TemporaryDirectory() as directory:
            root = Path(directory); source = root / "source"; source.mkdir(); path = source / "one.txt"
            path.write_text("needle")
            fake = FakeEmbedder(); app = compose(RuntimeConfig(root / "db", source, semantic_embedder=fake))
            item = next(app.connector.read()); app.service.ingest(item, "index")
            doc = app.store.get("one.txt"); assert doc is not None
            app.store.save_embedding(doc, fake.model, (1.0, 0.0), input_hash(doc.title, doc.text))
            app.service.revoke_source("one.txt")
            self.assertEqual([], app.service.search("needle", "reader"))
            # New content version removes old row before any new embedding is built.
            path.write_text("changed")
            app.service.ingest(next(app.connector.read()), "index")
            self.assertEqual(0, len(app.store.embedding_rows(fake.model)))
            app.service.tombstone("one.txt", "reader")
            self.assertEqual(0, len(app.store.embedding_rows(fake.model)))

    def test_ollama_embedding_validates_dimensions_and_malformed_response(self):
        class Response:
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def read(self, limit): return json.dumps({"embeddings": [[1.0], [1.0, 2.0]]}).encode()
        with patch("kb_pipeline.embedding._open_local", return_value=Response()):
            with self.assertRaises(EmbeddingValidationError): OllamaEmbedder("embeddinggemma").embed(("a", "b"))

    def test_cli_reindex_builds_durable_rows_without_ingest(self):
        with TemporaryDirectory() as directory:
            root = Path(directory); source = root / "source"; source.mkdir(); (source / "one.txt").write_text("semantic text")
            app = compose(RuntimeConfig(root / "db", source))
            for item in app.connector.read(): app.service.ingest(item, "index")
            result = _semantic_reindex(root / "db", FakeEmbedder())
            self.assertEqual(1, result["embedded"])
            self.assertEqual(1, len(app.store.embedding_rows("fake-semantic")))


if __name__ == "__main__": unittest.main()
