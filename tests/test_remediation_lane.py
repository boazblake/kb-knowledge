import unittest

from kb_pipeline.nango_adapter import FakeNangoTransport, NangoAdapter, NangoPoll
from kb_pipeline.protocol import OpaqueCursorSemantics, ObjectKey


class CursorAndNamespaceTests(unittest.TestCase):
    def test_numeric_cursor_is_connector_ordered_not_lexical(self):
        semantics = NangoAdapter("github", "source", "tenant").cursor_semantics
        self.assertGreater(semantics.compare("10", "2"), 0)
        self.assertEqual("nango-numeric-v1", semantics.version)

    def test_opaque_cursor_rejects_guessed_order(self):
        with self.assertRaises(ValueError):
            OpaqueCursorSemantics().compare("b", "a")

    def test_purge_identity_contains_all_namespace_parts(self):
        key = ObjectKey("github", "tenant-a", "nango", "source-a", "object").encoded()
        other = ObjectKey("github", "tenant-b", "nango", "source-a", "object").encoded()
        self.assertNotEqual(key, other)
        self.assertNotIn("tenant-b", key)

    def test_batch_exposes_connector_cursor_semantics(self):
        adapter = NangoAdapter("github", "source", "tenant")
        adapter = NangoAdapter("github", "source", "tenant", FakeNangoTransport((NangoPoll("10", ()),)))
        self.assertEqual("nango-numeric-v1", adapter.poll().cursor_semantics.version)  # type: ignore[union-attr]


if __name__ == "__main__":
    unittest.main()
