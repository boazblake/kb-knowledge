import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from kb_pipeline.adapters import ContentAwareCanonicalizer, LocalFilesConnector, PlainTextCanonicalizer, source_version
from kb_pipeline.composition import RuntimeConfig, compose
from kb_pipeline.domain import ACL, Input, RawRecord
from kb_pipeline.service import KnowledgeService
from kb_pipeline.storage import LexicalIndex, MemoryAuditStore, MemoryDocumentStore


class Resolver:
    def resolve(self, record): return ACL(frozenset({"reader"}))


def jpeg(marker=b""):
    return b"\xff\xd8\xff\xc0\x00\x0b\x08\x00\x02\x00\x03\x01\x01\x11\x00" + marker + b"\xff\xd9"


class ImageOnboardingTests(unittest.TestCase):
    def test_jpeg_metadata_placeholder_and_no_binary_decode(self):
        with TemporaryDirectory() as directory:
            root = Path(directory); image = root / "photo.jpg"
            payload = jpeg(bytes(range(32)))
            image.write_bytes(payload)
            item = next(LocalFilesConnector(root).read())
            self.assertEqual("image/jpeg", item.metadata["mime_type"])
            self.assertEqual(str(len(payload)), item.metadata["byte_length"])
            document = ContentAwareCanonicalizer().canonicalize(
                RawRecord(source_version(item), payload, item.metadata), ACL(frozenset({"reader"})))
            self.assertIn("visual extraction pending", document.text)
            self.assertNotIn("\ufffd", document.text)

    def test_raw_jpeg_persists_and_changed_path_reingests_but_duplicate_does_not(self):
        with TemporaryDirectory() as directory:
            root = Path(directory); source = root / "source"; source.mkdir(); path = source / "photo.jpg"
            path.write_bytes(jpeg(b"first"))
            app = compose(RuntimeConfig(root / "db", source))
            first = next(app.connector.read())
            self.assertTrue(app.service.ingest(first, "index"))
            path.write_bytes(jpeg(b"second"))
            second = next(app.connector.read())
            self.assertTrue(app.service.ingest(second, "index"))
            self.assertFalse(app.service.ingest(second, "different-job"))
            self.assertEqual(2, app.store.status()["raw_records"])
            raw = app.store.db.execute("SELECT artifact FROM raw_records").fetchall()
            self.assertEqual({jpeg(b"first"), jpeg(b"second")},
                             {Path(row[0]).read_bytes() for row in raw})
            self.assertTrue(app.service.search("visual extraction", "reader"))

    def test_existing_text_behavior_unchanged_and_unsupported_binary_rejected(self):
        service = KnowledgeService(MemoryDocumentStore(), LexicalIndex(), Resolver(), PlainTextCanonicalizer(), MemoryAuditStore())
        text = Input("test", "note.txt", b"plain text", "file:///note.txt")
        self.assertTrue(service.ingest(text, "text"))
        self.assertTrue(service.search("plain", "reader"))
        binary = Input("test", "bad.bin", b"\x00\xff\x00", "file:///bad.bin")
        with self.assertRaises(ValueError): service.ingest(binary, "binary")


if __name__ == "__main__":
    unittest.main()
