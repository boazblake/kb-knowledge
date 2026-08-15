import tempfile
import unittest
from pathlib import Path

from kb_pipeline.composition import RuntimeConfig
from kb_pipeline.ingestion_slice import IngestionSlice
from kb_pipeline.nango_adapter import FakeNangoTransport, NangoAdapter, NangoPoll, NangoRecord
from kb_pipeline.production_adapters import FixtureWorkflowBoundary
from kb_pipeline.protocol import Operation


class P3CompositionTests(unittest.TestCase):
    def test_production_rejects_local_authority_and_fixture_transport(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = dict(database=Path(tmp) / "state.sqlite", source_root=Path(tmp), mode="production")
            with self.assertRaisesRegex(ValueError, "SQLite"):
                RuntimeConfig(**base).validate()
            base["database"] = "postgresql://authority/db"
            base.update(raw_storage=object(), workflow=object(), telemetry=object(),
                        telemetry_endpoint="http://otel:4318", telemetry_service_name="kb",
                        identity_provider=object(), key_provider=object(), payload_provider=object(),
                        connector=FakeNangoTransport(()))
            with self.assertRaisesRegex(ValueError, "fixture|test/demo"):
                RuntimeConfig(**base).validate()

    def test_slice_acknowledges_only_after_service_acceptance(self):
        with tempfile.TemporaryDirectory() as tmp:
            from kb_pipeline.composition import compose
            config = RuntimeConfig(Path(tmp) / "state.sqlite", Path(tmp), mode="slice")
            composition = compose(config)
            adapter = NangoAdapter("github", "connection", "tenant",
                                   FakeNangoTransport((NangoPoll("c1", (NangoRecord("doc", {"title": "T", "text": "body"}),), run_id="run"),)))
            workflow = FixtureWorkflowBoundary()
            batch, accepted = IngestionSlice(adapter, composition.service, workflow).poll_once("job-1")
            self.assertTrue(accepted)
            self.assertEqual("c1", adapter.cursor)
            self.assertEqual("job-1", workflow.started[0][0])
            self.assertIsNotNone(composition.store.get("doc"))
            self.assertFalse(IngestionSlice(adapter, composition.service, workflow).poll_once("job-2")[1] is False)


if __name__ == "__main__":
    unittest.main()
