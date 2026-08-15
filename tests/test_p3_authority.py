import os
import unittest
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from kb_pipeline.nango_adapter import FakeNangoTransport, NangoAdapter, NangoPoll
from kb_pipeline.postgres_authority import MigrationRunner, PostgresAuthorityRepository, PostgresUnavailable
from kb_pipeline.protocol import IdentityNamespace


class P3AuthorityUnitTests(unittest.TestCase):
    def test_namespace_checkpoint_key_includes_tenant_and_source_instance(self):
        source = IdentityNamespace("github", "tenant-a", connector="nango", source_instance="conn-1")
        self.assertEqual(("github", "tenant-a", "nango", "conn-1", "doc"),
                         PostgresAuthorityRepository.object_key(source, "doc"))

    def test_cursor_is_loaded_and_saved_only_after_ack(self):
        class CursorStore:
            def __init__(self): self.saved = None
            def get_checkpoint(self, source): return self.saved
            def checkpoint(self, connector, value, complete, *, source): self.saved = (value, complete)

        store = CursorStore()
        adapter = NangoAdapter("github", "conn", "tenant", FakeNangoTransport((NangoPoll("c1", ()),)), cursor_store=store)
        batch = adapter.poll()
        adapter.acknowledge(batch, ledger_accepted=False)
        self.assertIsNone(store.saved)
        adapter.acknowledge(batch, ledger_accepted=True)
        self.assertEqual(("c1", True), store.saved)
        restarted = NangoAdapter("github", "conn", "tenant", FakeNangoTransport((NangoPoll("c2", ()),)), cursor_store=store)
        self.assertEqual("c1", restarted.cursor)

    def test_non_postgres_dsn_fails_closed_before_driver_use(self):
        with self.assertRaisesRegex(ValueError, "PostgreSQL DSN"):
            PostgresAuthorityRepository("sqlite:///state.db")

    def test_production_dependency_shape_is_checked(self):
        from kb_pipeline.composition import RuntimeConfig
        with self.assertRaisesRegex(ValueError, "incompatible adapter"):
            RuntimeConfig(
                database="postgresql://authority/db", source_root=Path.cwd(), mode="production",
                identity_provider=object(), key_provider=object(), payload_provider=object(),
                raw_storage=object(), workflow=object(), telemetry=object(), connector=object(),
                telemetry_endpoint="http://otel:4318", telemetry_service_name="kb",
            ).validate()

    @unittest.skipUnless(os.getenv("P3_POSTGRES_DSN"), "P3_POSTGRES_DSN not set; PostgreSQL runtime blocker")
    def test_migrations_are_idempotent_on_local_postgres(self):
        repo = PostgresAuthorityRepository(os.environ["P3_POSTGRES_DSN"])
        try:
            repo.open()
            with repo.transaction() as conn:
                self.assertEqual((), MigrationRunner().run(conn))
        finally:
            repo.close()

    @unittest.skipUnless(os.getenv("P3_POSTGRES_DSN"), "P3_POSTGRES_DSN not set; PostgreSQL runtime blocker")
    def test_accept_duplicate_gap_and_retry_state_on_local_postgres(self):
        from kb_pipeline.domain import ACL, CanonicalDocument, SourceVersion
        from kb_pipeline.protocol import CanonicalChange, Operation, PermissionState, ProvenanceLink
        repo = PostgresAuthorityRepository(os.environ["P3_POSTGRES_DSN"])
        suffix = uuid4().hex
        tenant = f"tenant-p3-{suffix}"
        workload = f"nango-{suffix}"
        source = IdentityNamespace("github", tenant, connector=workload, source_instance=f"conn-{suffix}")
        object_id = f"obj-{suffix}"
        observed = datetime.now(timezone.utc)
        document = CanonicalDocument(object_id, SourceVersion(object_id, "1", "nango://obj", observed, "hash"),
                                     "title", "body", ACL(frozenset({"reader"})))
        def change(revision, key):
            return CanonicalChange(object_id, source, revision, Operation.UPSERT, document, key,
                                   ProvenanceLink("test", key), PermissionState(document.acl), occurred_at=observed)
        try:
            repo.open()
            self.assertEqual("accepted", repo.accept(change(1, f"{suffix}-1"), raw_object_uri="nango://obj", content_hash="hash").value)
            self.assertEqual("duplicate", repo.accept(change(1, f"{suffix}-1"), raw_object_uri="nango://obj", content_hash="hash").value)
            self.assertEqual("gap", repo.accept(change(3, f"{suffix}-3"), raw_object_uri="nango://obj", content_hash="hash").value)
            claimed = repo.claim_outbox("test", tenant=tenant, workload=workload)
            self.assertEqual(1, len(claimed))
            repo.mark_outbox_failed(claimed[0]["sequence"], "downstream", max_attempts=1)
        finally:
            repo.close()

    @unittest.skipUnless(os.getenv("P3_POSTGRES_DSN"), "P3_POSTGRES_DSN not set; PostgreSQL runtime blocker")
    def test_claim_outbox_scope_limit_worker_and_expired_lease_reclaim(self):
        repo = PostgresAuthorityRepository(os.environ["P3_POSTGRES_DSN"])
        suffix = uuid4().hex
        tenant = f"claim-tenant-{suffix}"
        other_tenant = f"claim-other-{suffix}"
        workload = f"claim-workload-{suffix}"
        try:
            repo.open()
            with repo.transaction() as conn:
                conn.execute("""INSERT INTO ingestion_outbox
                    (idempotency_key, object_key, tenant, workload, payload)
                    VALUES (%s, %s, %s, %s, %s), (%s, %s, %s, %s, %s),
                           (%s, %s, %s, %s, %s)""",
                             (f"{suffix}-1", f"object-{suffix}-1", tenant, workload, "{}",
                              f"{suffix}-2", f"object-{suffix}-2", tenant, workload, "{}",
                              f"{suffix}-3", f"object-{suffix}-3", other_tenant, workload, "{}"))

            claimed = repo.claim_outbox("worker-test", tenant=tenant, workload=workload, limit=1)
            self.assertEqual(1, len(claimed))
            self.assertEqual("worker-test", claimed[0]["worker"])
            self.assertEqual(tenant, claimed[0]["tenant"])
            self.assertEqual(workload, claimed[0]["workload"])

            second = repo.claim_outbox("worker-test", tenant=tenant, workload=workload, limit=10)
            self.assertEqual(1, len(second))
            self.assertEqual((), repo.claim_outbox("worker-test", tenant=tenant,
                                                   workload=workload, limit=10))
            other_claimed = repo.claim_outbox("worker-other", tenant=other_tenant,
                                              workload=workload, limit=10)
            self.assertEqual(1, len(other_claimed))
            self.assertEqual(other_tenant, other_claimed[0]["tenant"])
            self.assertEqual((), repo.claim_outbox("worker-other", tenant=other_tenant,
                                                   workload="wrong-workload", limit=10))
            with repo.transaction() as conn:
                conn.execute("""UPDATE ingestion_outbox
                    SET lease_expires_at = now() - interval '1 second'
                    WHERE sequence=%s""", (claimed[0]["sequence"],))

            reclaimed = repo.claim_outbox("worker-recovery", tenant=tenant, workload=workload, limit=10)
            self.assertEqual(1, len(reclaimed))
            self.assertEqual("worker-recovery", reclaimed[0]["worker"])
            self.assertEqual(claimed[0]["sequence"], reclaimed[0]["sequence"])
        finally:
            repo.close()


if __name__ == "__main__":
    unittest.main()
