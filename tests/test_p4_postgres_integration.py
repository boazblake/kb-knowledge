"""Disposable PostgreSQL P4 evidence; no live providers or network calls.

Run with ``P3_POSTGRES_DSN`` in Nix PostgreSQL environment. Each test resets
only P4/authority rows it owns, so suite can use disposable database.
"""

from __future__ import annotations

import hashlib
import os
import unittest
from datetime import datetime, timezone

from kb_pipeline.phase4_core import (
    BarrierState,
    EnvelopeOperation,
    PostgresFTSQueryService,
    PostgresProjectionWorker,
    ProjectionBarrier,
    QueryResultDTO,
    ReplayEnvelope,
    SemanticIdentity,
    verify_citation,
)
from kb_pipeline.postgres_authority import MigrationRunner
from kb_pipeline.temporal_ingestion import manual_retry_dead_letter
from kb_pipeline.security import AuthorizationError, Principal
try:
    from psycopg.types.json import Jsonb
except ImportError:  # PostgreSQL suite skips outside Nix/test dependency set.
    Jsonb = lambda value: value


DSN = os.getenv("P3_POSTGRES_DSN")


class _AuthorityConnection:
    """Expose real PostgreSQL execute plus authority revision lookup."""

    def __init__(self, connection):
        self.connection = connection

    def execute(self, *args, **kwargs):
        return self.connection.execute(*args, **kwargs)

    def authority_revision(self, identity):
        row = self.connection.execute(
            """SELECT revision FROM ingestion_authority
               WHERE tenant=%s AND connector=%s AND object_id=%s
                 AND provider=%s AND source_instance=%s""",
            (identity.tenant, identity.source, identity.source_id, "p4", "local"),
        ).fetchone()
        return row[0] if row else None


@unittest.skipUnless(DSN, "P3_POSTGRES_DSN not set; disposable PostgreSQL required")
class P4PostgresIntegrationTests(unittest.TestCase):
    """E2E-001..010 and P4-03..P4-09 executable traceability."""

    @classmethod
    def setUpClass(cls):
        import psycopg

        cls.connection = psycopg.connect(DSN)
        from kb_pipeline.postgres_authority import PostgresAuthorityRepository
        cls.repository = PostgresAuthorityRepository(DSN)
        cls.repository.open()
        with cls.connection.transaction():
            MigrationRunner().run(cls.connection)

    @classmethod
    def tearDownClass(cls):
        cls.connection.close()
        cls.repository.close()

    def setUp(self):
        # Close implicit read transactions from prior tests before TRUNCATE.
        self.connection.commit()
        with self.connection.transaction():
            self.connection.execute("""TRUNCATE p4_document, p4_projection_checkpoints, p4_identity_aliases, ingestion_authority,
                ingestion_outbox, ingestion_dead_letters, ingestion_audit, ingestion_idempotency RESTART IDENTITY""")

    def envelope(self, revision=1, operation=EnvelopeOperation.UPSERT, *, tenant="tenant-a",
                 source="docs", source_id="doc-1", text="alpha searchable", readers=("alice",),
                 content_hash=None):
        content_hash = content_hash or hashlib.sha256(text.encode()).hexdigest()
        return ReplayEnvelope(
            f"event-{tenant}-{source_id}-{revision}-{operation.value}",
            f"idem-{tenant}-{source_id}-{revision}-{operation.value}",
            SemanticIdentity(tenant, source, source_id), revision, operation,
            {"title": source_id, "text": text},
            {"uri": f"s3://raw/{tenant}/{source_id}", "content_hash": content_hash},
            {"provider": "p4", "connector": source, "source_instance": "local"},
            {"readers": list(readers), "admins": []}, f"corr-{revision}",
            datetime.now(timezone.utc),
        )

    def apply(self, envelope, sequence=None):
        worker = PostgresProjectionWorker(self.connection)
        with self.connection.transaction():
            if sequence is None:
                worker.apply(envelope)
            else:
                worker.apply_at_sequence(sequence, envelope)

    def authority(self, identity, revision):
        with self.connection.transaction():
            self.connection.execute(
                """INSERT INTO ingestion_authority
                   (provider,tenant,connector,source_instance,object_id,revision,operation,
                    payload,raw_object_uri,content_hash,observed_at,object_key)
                   VALUES (%s,%s,%s,%s,%s,%s,'upsert',%s,%s,%s,now(),%s)""",
                ("p4", identity.tenant, identity.source, "local", identity.source_id,
                 revision, Jsonb({"text": "alpha searchable"}), "s3://raw", "hash",
                 __import__("json").dumps(["p4", identity.tenant, identity.source, "local", identity.source_id])),
            )

    def test_e2e001_p4_03_worker_fts_and_projection_barrier(self):
        """Authority commit feeds worker, FTS, checkpoint, and freshness barrier."""
        self.apply(self.envelope(), sequence=1)
        barrier = ProjectionBarrier(accepted=1, applied=1)
        result = PostgresFTSQueryService(self.connection, barrier=barrier).search(
            Principal("alice", "tenant-a", source_scopes=frozenset({"docs"})), "searchable", source="docs", min_sequence=1)
        self.assertEqual("doc-1", result[0].identity.source_id)
        self.assertEqual(BarrierState.FRESH, barrier.observe(1).state)

    def test_e2e002_p4_04_acl_before_limit_and_tenant_isolation(self):
        """Unauthorized high-ranked rows cannot consume authorized result limit."""
        for tenant, source_id, text, readers in (
            ("tenant-a", "allowed", "alpha alpha", ("alice",)),
            ("tenant-a", "hidden", "alpha alpha alpha", ("bob",)),
            ("tenant-b", "foreign", "alpha alpha alpha alpha", ("alice",)),
        ):
            self.apply(self.envelope(tenant=tenant, source_id=source_id, text=text, readers=readers))
        principal = Principal("alice", "tenant-a", source_scopes=frozenset({"docs"}))
        results = PostgresFTSQueryService(self.connection, barrier=ProjectionBarrier()).search(principal, "alpha", source="docs", limit=1)
        self.assertEqual(("tenant-a", "allowed"), (results[0].identity.tenant, results[0].identity.source_id))

    def test_e2e003_p4_06_barrier_blocks_until_watermark(self):
        """Search cannot pass required projection watermark early."""
        with self.assertRaises(TimeoutError):
            PostgresFTSQueryService(self.connection, barrier=ProjectionBarrier(accepted=4, applied=3)).search(
                Principal("alice", "tenant-a", source_scopes=frozenset({"docs"})), "alpha", source="docs", min_sequence=4)

    def test_e2e004_p4_07_update_delete_revision_guard(self):
        """New update wins; stale replay cannot resurrect tombstoned document."""
        self.apply(self.envelope(1, text="old"))
        self.apply(self.envelope(2, text="new"))
        self.apply(self.envelope(1, text="stale"))
        self.apply(self.envelope(3, operation=EnvelopeOperation.DELETE, text="new"))
        self.apply(self.envelope(2, text="replayed"))
        row = self.connection.execute("SELECT revision,tombstoned FROM p4_document WHERE source_id='doc-1'").fetchone()
        self.assertEqual((3, True), row)

    def test_e2e005_replay_is_idempotent_and_tombstone_persists(self):
        """Repeated delete replay leaves one current tombstone."""
        delete = self.envelope(2, operation=EnvelopeOperation.DELETE)
        self.apply(self.envelope())
        self.apply(delete)
        self.apply(delete)
        self.assertEqual((1, 2), self.connection.execute(
            "SELECT count(*),max(revision) FROM p4_document WHERE source_id='doc-1'").fetchone())

    def test_e2e006_p4_08_citation_hash_acl_and_authority_validation(self):
        """Citation accepts current authority/hash and rejects each stale variant."""
        text = "citation body"
        content_hash = hashlib.sha256(text.encode()).hexdigest()
        envelope = self.envelope(text=text, content_hash=content_hash)
        identity = envelope.semantic_key
        self.apply(envelope)
        self.authority(identity, 1)
        with self.connection.transaction():
            self.connection.execute("UPDATE ingestion_authority SET raw_object_uri=%s,content_hash=%s WHERE tenant=%s AND connector=%s AND object_id=%s",
                                    ("s3://raw/tenant-a/doc-1", content_hash, "tenant-a", "docs", "doc-1"))
        principal = Principal("alice", "tenant-a", source_scopes=frozenset({"docs"}))
        result = PostgresFTSQueryService(self.connection, barrier=ProjectionBarrier()).search(principal, "citation", source="docs")[0]
        self.assertTrue(verify_citation(_AuthorityConnection(self.connection), principal, result))
        self.assertFalse(verify_citation(self.connection, Principal("alice", "tenant-b", source_scopes=frozenset({"docs"})), result))
        self.assertFalse(verify_citation(self.connection, principal, QueryResultDTO(
            result.identity, 1, result.score, result.title, result.snippet, result.provenance,
            {"raw_reference": {"content_hash": "wrong"}})))
        with self.connection.transaction():
            self.connection.execute("UPDATE ingestion_authority SET revision=2")
        self.assertFalse(verify_citation(_AuthorityConnection(self.connection), principal, result))

    def test_e2e007_worker_failure_does_not_write_projection(self):
        """Injected failure remains visible to caller and writes no row."""
        worker = PostgresProjectionWorker(self.connection, failure=lambda _: (_ for _ in ()).throw(RuntimeError("down")))
        with self.assertRaisesRegex(RuntimeError, "down"), self.connection.transaction():
            worker.apply(self.envelope())
        self.assertIsNone(self.connection.execute("SELECT 1 FROM p4_document").fetchone())

    def test_e2e007_p4_09_retry_bounded_dlq_authorized_recovery_and_tombstone(self):
        """E2E-007/P4-09: retry -> bounded DLQ -> operator replay -> safe recovery."""
        delete = self.envelope(2, operation=EnvelopeOperation.DELETE)
        with self.connection.transaction():
            # Authority is the unchanged source of truth throughout projection recovery.
            self.connection.execute("""INSERT INTO ingestion_authority
                (provider,tenant,connector,source_instance,object_id,revision,operation,
                 payload,raw_object_uri,content_hash,observed_at,object_key)
                VALUES ('p4','tenant-a','docs','local','doc-1',2,'delete',NULL,'s3://raw','hash',now(),
                        '["p4", "tenant-a", "docs", "local", "doc-1"]')""")
            self.connection.execute("""INSERT INTO ingestion_outbox
                (idempotency_key,object_key,tenant,workload,payload,envelope)
                VALUES (%s,%s,%s,%s,%s,%s)""",
                (delete.idempotency_key, "p4:tenant-a:docs:local:doc-1", "tenant-a", "docs",
                 Jsonb({}), Jsonb(delete.as_dict())))
        authority_before = self.connection.execute(
            """SELECT revision,operation,payload FROM ingestion_authority
             WHERE provider='p4' AND tenant='tenant-a' AND connector='docs'
               AND source_instance='local' AND object_id='doc-1'"""
        ).fetchone()
        sequence = self.connection.execute(
            "SELECT sequence FROM ingestion_outbox WHERE idempotency_key=%s", (delete.idempotency_key,)
        ).fetchone()[0]
        failures = {"remaining": 3}

        def fail_deterministically(_):
            if failures["remaining"]:
                failures["remaining"] -= 1
                raise RuntimeError("injected projection failure")

        worker = PostgresProjectionWorker(self.connection, failure=fail_deterministically)
        for expected_attempt in (1, 2, 3):
            claimed = self._claim_until_available(sequence, f"p4-worker-{expected_attempt}")
            self.assertEqual(expected_attempt, claimed["attempts"])
            with self.assertRaisesRegex(RuntimeError, "injected projection failure"):
                with self.connection.transaction():
                    worker.apply_at_sequence(sequence, delete)
            with self.connection.transaction():
                self.connection.execute("""UPDATE ingestion_outbox SET available_at=now()
                    WHERE sequence=%s AND status='pending'""", (sequence,))
            self._mark_failed(sequence, claimed)

        state = self.connection.execute(
            "SELECT status,attempts FROM ingestion_outbox WHERE sequence=%s", (sequence,)
        ).fetchone()
        self.assertEqual(("dead", 3), state)
        self.assertEqual((1,), self.connection.execute(
            "SELECT count(*) FROM ingestion_dead_letters WHERE sequence=%s", (sequence,)
        ).fetchone())
        self.assertIsNone(self.connection.execute(
            "SELECT sequence FROM p4_projection_checkpoints WHERE projection='document'"
        ).fetchone(), "failed transaction must not advance watermark")
        self.assertEqual(authority_before, self.connection.execute(
            """SELECT revision,operation,payload FROM ingestion_authority
             WHERE provider='p4' AND tenant='tenant-a' AND connector='docs'
               AND source_instance='local' AND object_id='doc-1'"""
        ).fetchone())

        with self.assertRaises(ValueError):
            manual_retry_dead_letter(self.repository, sequence, operator=" ")
        manual_retry_dead_letter(self.repository, sequence, operator="oncall")
        recovered = self._claim_until_available(sequence, "p4-recovery")
        recovery_worker = PostgresProjectionWorker(self.connection)
        with self.connection.transaction():
            recovery_worker.apply_at_sequence(sequence, delete)
        self.repository.mark_outbox_applied(sequence, recovered["worker"], tenant=recovered["tenant"],
                                            workload=recovered["workload"], lease_token=recovered["lease_token"])
        self.assertEqual(("applied", 1), self.connection.execute(
            "SELECT status,attempts FROM ingestion_outbox WHERE sequence=%s", (sequence,)
        ).fetchone())
        self.assertEqual((2, sequence, "fresh"), self.connection.execute(
            """SELECT revision,sequence,state FROM p4_document d JOIN p4_projection_checkpoints c ON c.projection='document'
             WHERE d.source_id='doc-1'"""
        ).fetchone())

        barrier = ProjectionBarrier(accepted=sequence, applied=sequence - 1)
        with self.assertRaises(TimeoutError):
            PostgresFTSQueryService(self.connection, barrier=barrier).search(
                Principal("alice", "tenant-a", source_scopes=frozenset({"docs"})), "alpha", source="docs", min_sequence=sequence)
        barrier.applied = sequence
        self.assertEqual(BarrierState.FRESH, barrier.observe(sequence).state)
        self.assertEqual((), PostgresFTSQueryService(self.connection, barrier=barrier).search(
            Principal("alice", "tenant-a", source_scopes=frozenset({"docs"})), "alpha", source="docs", min_sequence=sequence))
        with self.connection.transaction():
            PostgresProjectionWorker(self.connection).apply(self.envelope(1, text="alpha searchable"))
        self.assertEqual((2, True), self.connection.execute(
            "SELECT revision,tombstoned FROM p4_document WHERE source_id='doc-1'"
        ).fetchone())

    def _claim_until_available(self, sequence, worker):
        # Read assertions use psycopg's implicit transaction; close it before
        # the repository's separate pool connection takes the lease lock.
        self.connection.commit()
        claimed = self.repository.claim_outbox(worker, tenant="tenant-a", workload="docs")
        self.assertEqual(1, len(claimed))
        self.assertEqual(sequence, claimed[0]["sequence"])
        return claimed[0]

    def _mark_failed(self, sequence, claimed):
        self.repository.mark_outbox_failed(sequence, "injected projection failure", claimed["worker"],
                                            tenant=claimed["tenant"], workload=claimed["workload"], lease_token=claimed["lease_token"],
                                            max_attempts=3, base_delay_seconds=0, jitter_seconds=0)

    def test_durable_barrier_blocks_stale_projection(self):
        self.apply(self.envelope(), sequence=1)
        with self.connection.transaction():
            self.connection.execute("""INSERT INTO ingestion_outbox
                (idempotency_key,object_key,tenant,workload,payload) VALUES
                ('new','new','tenant-a','docs',%s), ('newer','newer','tenant-a','docs',%s)""", (Jsonb({}), Jsonb({})))
        with self.assertRaises(TimeoutError):
            PostgresFTSQueryService(self.connection).search(
                Principal("alice", "tenant-a", source_scopes=frozenset({"docs"})), "searchable", source="docs")

    def test_lease_completion_failure_cannot_cross_scope_with_reused_worker(self):
        with self.connection.transaction():
            self.connection.execute("""INSERT INTO ingestion_outbox
                (idempotency_key,object_key,tenant,workload,payload) VALUES ('scope-a','a','tenant-a','docs',%s)""", (Jsonb({}),))
        claimed = self.repository.claim_outbox("same-worker", tenant="tenant-a", workload="docs")[0]
        with self.assertRaises(PermissionError):
            self.repository.mark_outbox_applied(claimed["sequence"], "same-worker", tenant="tenant-b",
                                                workload="docs", lease_token=claimed["lease_token"])
        with self.assertRaises(PermissionError):
            self.repository.mark_outbox_failed(claimed["sequence"], "cross-scope", "same-worker",
                                               tenant="tenant-b", workload="docs", lease_token=claimed["lease_token"])

    def test_e2e008_p4_03_schema_is_disposable_and_repeatable(self):
        """Migration and P4 tables are available on disposable PostgreSQL."""
        self.assertEqual(1, self.connection.execute("SELECT count(*) FROM pg_tables WHERE tablename='p4_document'").fetchone()[0])

    def test_e2e009_p4_05_source_filter_is_enforced(self):
        """Source scope and SQL source predicate isolate FTS results."""
        self.apply(self.envelope(source="docs"))
        self.apply(self.envelope(source="mail", source_id="mail-1"))
        principal = Principal("alice", "tenant-a", source_scopes=frozenset({"docs", "mail"}))
        results = PostgresFTSQueryService(self.connection, barrier=ProjectionBarrier()).search(principal, "alpha", source="mail")
        self.assertEqual(["mail-1"], [item.identity.source_id for item in results])

    def test_e2e010_p4_09_missing_source_scope_fails_closed(self):
        """Principal without source scope cannot issue scoped search."""
        with self.assertRaises(AuthorizationError):
            PostgresFTSQueryService(self.connection).search(Principal("alice", "tenant-a"), "alpha", source="docs")

    def test_namespace_alias_collision_fails_closed(self):
        self.apply(self.envelope())
        colliding = self.envelope()
        colliding = ReplayEnvelope(colliding.event_id + "-other", colliding.idempotency_key + "-other",
                                   colliding.semantic_key, 2, colliding.operation, colliding.payload,
                                   colliding.raw_reference,
                                   {"provider": "other", "connector": "docs", "source_instance": "local"},
                                   colliding.permissions, colliding.correlation_id, colliding.observed_at)
        with self.assertRaises(ValueError):
            with self.connection.transaction():
                PostgresProjectionWorker(self.connection).apply(colliding)

    def test_projection_checkpoint_rejects_skipped_sequence(self):
        self.apply(self.envelope(), sequence=1)
        with self.assertRaises(ValueError):
            with self.connection.transaction():
                PostgresProjectionWorker(self.connection).apply_at_sequence(12, self.envelope(2))

    def test_citation_requires_nonempty_reference(self):
        self.apply(self.envelope())
        principal = Principal("alice", "tenant-a", source_scopes=frozenset({"docs"}))
        result = PostgresFTSQueryService(self.connection, barrier=ProjectionBarrier()).search(principal, "alpha", source="docs")[0]
        self.assertFalse(verify_citation(self.connection, principal, QueryResultDTO(
            result.identity, result.revision, result.score, result.title, result.snippet,
            result.provenance, {"raw_reference": {"content_hash": ""}})))

    def test_citation_rejects_cross_namespace_provenance_tampering(self):
        envelope = self.envelope()
        self.apply(envelope)
        self.authority(envelope.semantic_key, 1)
        principal = Principal("alice", "tenant-a", source_scopes=frozenset({"docs"}))
        result = PostgresFTSQueryService(self.connection, barrier=ProjectionBarrier()).search(principal, "alpha", source="docs")[0]
        with self.connection.transaction():
            self.connection.execute("UPDATE ingestion_authority SET raw_object_uri=%s,content_hash=%s",
                                    (result.citation["raw_reference"]["uri"],
                                     result.citation["raw_reference"]["content_hash"]))
        for field, value in (("provider", "other-provider"), ("connector", "other-connector"),
                             ("source_instance", "other-instance")):
            provenance = dict(result.provenance)
            provenance[field] = value
            tampered = QueryResultDTO(result.identity, result.revision, result.score, result.title,
                                      result.snippet, provenance, result.citation)
            self.assertFalse(verify_citation(self.connection, principal, tampered), field)

    def test_expired_lease_reaping_is_tenant_workload_scoped(self):
        with self.connection.transaction():
            self.connection.execute("""INSERT INTO ingestion_outbox
              (idempotency_key,object_key,tenant,workload,payload,status,lease_owner,lease_expires_at)
              VALUES (%s,%s,%s,%s,%s,'claimed','old',now()-interval '1 second'),
                     (%s,%s,%s,%s,%s,'claimed','old',now()-interval '1 second')""",
              ("lease-a", "a", "tenant-a", "docs", Jsonb({}),
               "lease-b", "b", "tenant-b", "docs", Jsonb({})))
        self.connection.commit()
        self.repository.claim_outbox("new", tenant="tenant-a", workload="docs")
        self.assertEqual(("claimed", "old"), self.connection.execute(
            "SELECT status,lease_owner FROM ingestion_outbox WHERE idempotency_key='lease-b'").fetchone())


if __name__ == "__main__":
    unittest.main()
