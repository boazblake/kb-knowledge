import unittest

from kb_pipeline.mock_environment import (
    MOCK_REFERENCE_BANNER, MockKMSProvider, MockOIDCIssuer,
    MockS3RawObjectStore, MockTemporalBoundary, MockTelemetrySink,
    mock_status,
)
from kb_pipeline.production_adapters import ArtifactContext, ManagedOIDCValidator
from kb_pipeline.security import AuthenticationError, EnvelopeError


class MockEnvironmentTests(unittest.TestCase):
    def test_status_is_explicitly_non_production(self):
        status = mock_status()
        self.assertEqual("MOCK/REFERENCE", status["classification"])
        self.assertEqual("forbidden", status["qualification"])
        self.assertIn("cannot qualify production", status["banner"])

    def test_rsa_oidc_rotation_and_jwks_failure_fail_closed(self):
        try:
            issuer = MockOIDCIssuer(); url = issuer.start()
        except RuntimeError as exc:
            self.skipTest(str(exc))
        try:
            validator = ManagedOIDCValidator(issuer.issuer, issuer.audience, url)
            self.assertEqual("mock-tenant", validator.validate(issuer.issue()).tenant)
            issuer.rotate("mock-rsa-2")
            self.assertEqual("mock-user", validator.validate(issuer.issue(kid="mock-rsa-2")).subject)
            issuer.fail_jwks = True
            issuer.rotate("mock-rsa-3")
            with self.assertRaises(AuthenticationError):
                validator.validate(issuer.issue(kid="mock-rsa-3"))
        finally:
            issuer.close()

    def test_mock_kms_and_s3_reuse_encrypted_s3_boundary(self):
        kms = MockKMSProvider(b"mock-kms-master-key-32-bytes------")
        store = MockS3RawObjectStore(kms=kms)
        context = ArtifactContext("mock-provider", "mock-tenant", "mock-connector", "mock-source", "obj-1", "1")
        key = context.key(store.prefix)
        self.assertTrue(store.put(key, b"synthetic", context=context).startswith("s3://"))
        self.assertEqual(b"synthetic", store.get(key, context=context))
        kms.fail()
        with self.assertRaises(EnvelopeError):
            store.put(context.key(store.prefix).replace("obj-1", "obj-2"), b"synthetic", context=ArtifactContext("mock-provider", "mock-tenant", "mock-connector", "mock-source", "obj-2", "1"))

    def test_workflow_duplicate_retry_and_telemetry_sink(self):
        boundary = MockTemporalBoundary(failures=1)
        with self.assertRaises(ConnectionError): boundary.start_ingestion("wf-1", {"tenant": "mock-tenant"})
        self.assertEqual("wf-1", boundary.start_ingestion("wf-1", {"tenant": "mock-tenant"}))
        with self.assertRaises(ValueError): boundary.start_ingestion("wf-1", {})
        sink = MockTelemetrySink()
        with sink.span("mock.workflow", tenant="mock-tenant", payload="must-not-be-exported"): pass
        sink.counter("mock.retry")
        self.assertEqual(1, len(sink.spans)); self.assertEqual(1, sink.counters["mock.retry"])


if __name__ == "__main__":
    unittest.main()
