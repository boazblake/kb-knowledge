"""MOCK/REFERENCE E2E lane; requires caller-provided local Nix PostgreSQL."""
import os
import unittest

from kb_pipeline.composition import RuntimeConfig, compose
from kb_pipeline.mock_environment import (ApprovedMockConnectorFixture, MockKMSProvider,
                                           MockOIDCIssuer, MockOIDCValidator, MockS3RawObjectStore,
                                           MockTemporalBoundary, MockTelemetrySink)
from kb_pipeline.postgres_authority import PostgresAuthorityRepository
from kb_pipeline.nango_adapter import NangoRecord
from kb_pipeline.protocol import Operation


@unittest.skipUnless(os.getenv("P3_POSTGRES_DSN"), "MOCK/REFERENCE E2E requires local Nix PostgreSQL")
class MockPostgresE2ETests(unittest.TestCase):
    def test_auth_connector_encrypt_store_authority_outbox_workflow_telemetry(self):
        try:
            issuer = MockOIDCIssuer(); jwks = issuer.start()
        except RuntimeError as exc:
            self.skipTest(str(exc))
        repo = PostgresAuthorityRepository(os.environ["P3_POSTGRES_DSN"])
        try:
            token = issuer.issue(source_scopes=("mock-connection",))
            connector = ApprovedMockConnectorFixture(
                oidc_token=token,
                records=(
                    NangoRecord("object-1", {"title": "synthetic", "text": "MOCK/REFERENCE v1"}, revision=1),
                    NangoRecord("object-1", {"title": "synthetic", "text": "MOCK/REFERENCE v2"}, revision=2),
                    NangoRecord("object-1", operation=Operation.DELETE, revision=3),
                    NangoRecord("object-1", permission_readers=frozenset({"reader"}),
                                operation=Operation.PERMISSION, revision=4),
                ))
            kms = MockKMSProvider(b"mock-kms-master-key-32-bytes------")
            raw = MockS3RawObjectStore(kms=kms)
            workflow, telemetry = MockTemporalBoundary(), MockTelemetrySink()
            app = compose(RuntimeConfig(
                os.environ["P3_POSTGRES_DSN"], None, mode="mock", connector=connector,
                authority_repository=repo, identity_provider=MockOIDCValidator(issuer.issuer, issuer.audience, jwks),
                key_provider=kms, raw_storage=raw, workflow=workflow, telemetry=telemetry))
            _, accepted = app.ingestion.poll_once("mock-job")
            self.assertFalse(accepted)  # default policy forbids resurrection after delete
            self.assertEqual(0, len(workflow.started))
            self.assertEqual(3, repo.queue_metrics(tenant="mock-tenant", workload="mock-connector")["queue_depth"])
            self.assertTrue(any(span["name"] == "auth.ingestion" for span in telemetry.spans))
            self.assertTrue(repo.raw_reference(connector.source, "object-1"))
            reference = repo.raw_reference(connector.source, "object-1")
            self.assertEqual(3, reference[2])
            uri = reference[0].decode() if isinstance(reference[0], bytes) else reference[0]
            key = uri.replace(f"s3://{raw.bucket}/", "")
            self.assertNotIn(b"MOCK/REFERENCE", raw.mock_client.objects[(raw.bucket, key)][0])
            self.assertEqual(b"{}", app.service.read_raw(connector.source, "object-1"))
        finally:
            repo.close(); issuer.close()


if __name__ == "__main__":
    unittest.main()
