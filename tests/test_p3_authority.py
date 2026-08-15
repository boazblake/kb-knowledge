import os
import unittest
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from kb_pipeline.nango_adapter import FakeNangoTransport, NangoAdapter, NangoPoll
from kb_pipeline.postgres_authority import (MigrationRunner, PostgresAuthorityRepository,
                                            PostgresUnavailable, _fingerprints_match,
                                            _normalize_fingerprint)
from kb_pipeline.protocol import IdentityNamespace, ObjectKey


@contextmanager
def _postgres_repository(dsn):
    repo = PostgresAuthorityRepository(dsn)
    try:
        repo.open()
        yield repo
    except BaseException:
        try:
            repo.close()
        except BaseException:
            pass
        raise
    else:
        repo.close()


@contextmanager
def _reopened_postgres_repository(repo):
    """Reopen persistence with a fresh pool; psycopg pools cannot be reopened."""
    repo.close()
    reopened = PostgresAuthorityRepository(repo.dsn, migrations_dir=repo.migrations.directory)
    try:
        reopened.open()
    except BaseException:
        try:
            reopened.close()
        except BaseException:
            pass
        raise
    try:
        yield reopened
    except BaseException:
        try:
            reopened.close()
        except BaseException:
            pass
        raise
    else:
        reopened.close()


class P3AuthorityUnitTests(unittest.TestCase):
    def test_fingerprint_normalization_is_strict(self):
        fingerprint = '{"content_hash":"hash"}'
        self.assertEqual(fingerprint, _normalize_fingerprint(fingerprint.encode("utf-8")))
        self.assertEqual(fingerprint, _normalize_fingerprint(memoryview(fingerprint.encode("utf-8"))))
        self.assertTrue(_fingerprints_match(fingerprint.encode("utf-8"), fingerprint))
        self.assertFalse(_fingerprints_match(b"not-the-fingerprint", fingerprint))
        self.assertIsNone(_normalize_fingerprint(b"\xff"))

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
    def test_migration_005_is_compatible_and_directly_idempotent(self):
        repo = PostgresAuthorityRepository(os.environ["P3_POSTGRES_DSN"])
        try:
            repo.open()
            migration = Path(__file__).parents[1] / "migrations" / "005_canonical_object_keys.sql"
            with repo.transaction() as conn:
                conn.execute(migration.read_text(encoding="utf-8"))
                conn.execute(migration.read_text(encoding="utf-8"))
                column = conn.execute("""SELECT attgenerated, attnotnull
                    FROM pg_attribute
                    WHERE attrelid='ingestion_authority'::regclass AND attname='object_key'""").fetchone()
                self.assertEqual(("", True), tuple(column))
        finally:
            repo.close()

    @unittest.skipUnless(os.getenv("P3_POSTGRES_DSN"), "P3_POSTGRES_DSN not set; PostgreSQL runtime blocker")
    def test_repository_writes_canonical_key_and_reads_exact_namespace(self):
        from kb_pipeline.domain import ACL, CanonicalDocument, SourceVersion
        from kb_pipeline.protocol import CanonicalChange, Operation, PermissionState, ProvenanceLink
        repo = PostgresAuthorityRepository(os.environ["P3_POSTGRES_DSN"])
        suffix = uuid4().hex
        observed = datetime.now(timezone.utc)
        try:
            repo.open()
            changes = []
            sources = (
                IdentityNamespace("provider-a", f"tenant-{suffix}", connector="connector", source_instance="source"),
                IdentityNamespace("provider-b", f"tenant-{suffix}", connector="connector", source_instance="source"),
                IdentityNamespace("provider-a", f"tenant-{suffix}", connector="other", source_instance="source"),
                IdentityNamespace("provider-a", f"tenant-{suffix}", connector="connector", source_instance="other"),
                IdentityNamespace("provider-a", f"other-{suffix}", connector="connector", source_instance="source"),
            )
            for index, source in enumerate(sources):
                document = CanonicalDocument("same-object", SourceVersion("same-object", "1", "source://object",
                                            observed, f"hash-{index}"), "title", "body", ACL(frozenset({"reader"})))
                change = CanonicalChange("same-object", source, 1, Operation.UPSERT, document, f"{suffix}-{index}",
                                         ProvenanceLink("test", suffix), PermissionState(document.acl), occurred_at=observed)
                self.assertEqual("accepted", repo.accept(change, raw_object_uri=f"source://{index}",
                                                          content_hash=f"hash-{index}").value)
                changes.append(change)
            with repo.transaction() as conn:
                rows = conn.execute("""SELECT provider,tenant,connector,source_instance,object_id,object_key
                    FROM ingestion_authority WHERE object_id=%s AND tenant LIKE %s""",
                                    ("same-object", f"%{suffix}")).fetchall()
            self.assertEqual(5, len(rows))
            for index, change in enumerate(changes):
                identity = (change.source.provider, change.source.tenant, change.source.connector,
                            change.source.source_instance, change.object_id)
                row = next(row for row in rows if row[:5] == identity)
                self.assertEqual(ObjectKey.from_change(change).encoded(), row[5])
                self.assertEqual((f"source://{index}", f"hash-{index}", 1, "upsert"),
                                 repo.raw_reference(change.source, change.object_id))
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
            with repo.transaction() as conn:
                stored_text = conn.execute(
                    "SELECT fingerprint FROM ingestion_idempotency WHERE idempotency_key=%s",
                    (f"{suffix}-1",),
                ).fetchone()[0]
                stored_bytes = conn.execute(
                    "SELECT convert_to(fingerprint, 'UTF8') FROM ingestion_idempotency "
                    "WHERE idempotency_key=%s",
                    (f"{suffix}-1",),
                ).fetchone()[0]
            self.assertIsInstance(stored_text, str)
            self.assertIsInstance(stored_bytes, bytes)
            self.assertTrue(_fingerprints_match(stored_bytes, stored_text))

            variants = ("tenant", "object", "revision", "content", "operation")
            for name in variants:
                scenario_source = source.__class__(source.provider, source.tenant, connector=f"{source.connector}-{name}",
                                                   source_instance=f"{source.source_instance}-{name}")
                scenario_object = f"{object_id}-{name}"
                scenario_document = CanonicalDocument(
                    scenario_object, SourceVersion(scenario_object, "1", "nango://obj", observed, "hash"),
                    "title", "body", ACL(frozenset({"reader"})))
                key = f"{suffix}-{name}"
                baseline = CanonicalChange(scenario_object, scenario_source, 1, Operation.UPSERT, scenario_document, key,
                                           ProvenanceLink("test", key), PermissionState(scenario_document.acl), occurred_at=observed)
                self.assertEqual("accepted", repo.accept(baseline, raw_object_uri="nango://obj", content_hash="hash").value)
                variant_source, variant_object, revision, operation, value, content_hash = scenario_source, scenario_object, 1, Operation.UPSERT, scenario_document, "hash"
                if name == "tenant":
                    variant_source = source.__class__(source.provider, f"tenant-{suffix}", connector=source.connector,
                                                      source_instance=scenario_source.source_instance)
                elif name == "object":
                    variant_object = f"other-{suffix}-{name}"
                elif name == "revision":
                    revision = 2
                elif name == "content":
                    value = CanonicalDocument(scenario_object, scenario_document.source, scenario_document.title, "changed", scenario_document.acl)
                    content_hash = "changed-hash"
                elif name == "operation":
                    operation, value = Operation.DELETE, None
                variant = CanonicalChange(variant_object, variant_source, revision, operation, value, key,
                                          ProvenanceLink("test", key), PermissionState(scenario_document.acl), occurred_at=observed)
                self.assertEqual("conflict", repo.accept(variant, raw_object_uri="nango://obj", content_hash=content_hash).value, name)

            self.assertEqual("gap", repo.accept(change(3, f"{suffix}-3"), raw_object_uri="nango://obj", content_hash="hash").value)
            claimed = repo.claim_outbox("test", tenant=tenant, workload=workload)
            self.assertEqual(1, len(claimed))
            repo.mark_outbox_failed(claimed[0]["sequence"], "downstream", claimed[0]["worker"], max_attempts=1)
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

    @unittest.skipUnless(os.getenv("P3_POSTGRES_DSN"), "P3_POSTGRES_DSN not set; PostgreSQL runtime blocker")
    def test_batch_gap_does_not_advance_checkpoint_and_skip_missing_revision(self):
        from kb_pipeline.domain import ACL, CanonicalDocument, SourceVersion
        from kb_pipeline.protocol import CanonicalChange, Operation, PermissionState, ProvenanceLink, RevisionOutcome

        class CursorOrder:
            def compare(self, left, right):
                return (left > right) - (left < right)

        repo = PostgresAuthorityRepository(os.environ["P3_POSTGRES_DSN"])
        suffix = uuid4().hex
        source = IdentityNamespace("provider", f"batch-{suffix}", connector="connector", source_instance="instance")
        observed = datetime.now(timezone.utc)
        document = CanonicalDocument("object", SourceVersion("object", "1", "source://object", observed, "hash"),
                                     "title", "body", ACL(frozenset({"reader"})))

        def change(revision):
            return CanonicalChange("object", source, revision, Operation.UPSERT, document, f"{suffix}-{revision}",
                                   ProvenanceLink("test", suffix), PermissionState(document.acl), occurred_at=observed)

        order = CursorOrder()
        try:
            repo.open()
            repo.checkpoint("connector", "c1", True, source=source, cursor_semantics=order)
            outcomes = repo.accept_batch(
                tuple((change(revision), f"source://{revision}", "hash", None) for revision in (1, 3)),
                checkpoint=(source, "c3", True), cursor_semantics=order)
            self.assertEqual((RevisionOutcome.ACCEPTED, RevisionOutcome.GAP), outcomes)
            self.assertEqual(("c1", True), repo.get_checkpoint(source))
            self.assertEqual(1, repo.raw_reference(source, "object")[2])

            outcomes = repo.accept_batch(
                tuple((change(revision), f"source://{revision}", "hash", None) for revision in (2, 3)),
                checkpoint=(source, "c3", True), cursor_semantics=order)
            self.assertEqual((RevisionOutcome.ACCEPTED, RevisionOutcome.ACCEPTED), outcomes)
            self.assertEqual(("c3", True), repo.get_checkpoint(source))
            self.assertEqual(3, repo.raw_reference(source, "object")[2])
        finally:
            repo.close()

    @unittest.skipUnless(os.getenv("P3_POSTGRES_DSN"), "P3_POSTGRES_DSN not set; PostgreSQL runtime blocker")
    def test_outbox_failure_requires_lease_owner(self):
        repo = PostgresAuthorityRepository(os.environ["P3_POSTGRES_DSN"])
        suffix = uuid4().hex
        try:
            repo.open()
            with repo.transaction() as conn:
                conn.execute("INSERT INTO ingestion_outbox (idempotency_key,object_key,tenant,workload,payload) VALUES (%s,%s,%s,%s,%s)", (suffix, "{}", "t", "c", "{}"))
            claimed = repo.claim_outbox("owner", tenant="t", workload="c")
            for worker in (None, "", "other"):
                with self.assertRaises(PermissionError):
                    repo.mark_outbox_failed(claimed[0]["sequence"], "downstream", worker)
            repo.mark_outbox_failed(claimed[0]["sequence"], "downstream", "owner", max_attempts=1)
        finally:
            repo.close()

    @unittest.skipUnless(os.getenv("P3_POSTGRES_DSN"), "P3_POSTGRES_DSN not set; PostgreSQL runtime blocker")
    def test_purge_tombstone_uses_full_namespace_and_blocks_replay(self):
        from kb_pipeline.domain import ACL, CanonicalDocument, SourceVersion
        from kb_pipeline.purge import PurgeIntent, RetentionDecision
        from kb_pipeline.protocol import CanonicalChange, Operation, PermissionState, ProvenanceLink
        suffix = uuid4().hex
        source = IdentityNamespace("provider", f"tenant-{suffix}", connector=f"connector-{suffix}", source_instance=f"source-{suffix}")
        observed = datetime.now(timezone.utc)
        document = CanonicalDocument("object", SourceVersion("object", "1", "source://object", observed, "hash"), "title", "body", ACL(frozenset({"reader"})))
        change = CanonicalChange("object", source, 1, Operation.UPSERT, document, f"{suffix}-1", ProvenanceLink("test", suffix), PermissionState(document.acl), occurred_at=observed)
        with _postgres_repository(os.environ["P3_POSTGRES_DSN"]) as repo:
            repo.accept(change, raw_object_uri="source://object", content_hash="hash")
            target = ObjectKey.from_change(change).encoded()
            repo.create_purge_intent(PurgeIntent(suffix, f"{suffix}-purge", target, "actor", "correlation", RetentionDecision("customer")))
            self.assertEqual((), repo.tombstone_for_purge(suffix, ObjectKey("provider", f"other-{suffix}", source.connector, source.source_instance, "object").encoded(), "actor", "correlation"))
            self.assertEqual((target,), repo.tombstone_for_purge(suffix, target, "actor", "correlation"))
            with _reopened_postgres_repository(repo) as reopened:
                with self.assertRaisesRegex(ValueError, "purged object"):
                    reopened.accept(change.__class__("object", source, 2, Operation.UPSERT, document, f"{suffix}-2", change.provenance, change.permissions, occurred_at=observed), raw_object_uri="source://object", content_hash="hash")


if __name__ == "__main__":
    unittest.main()
