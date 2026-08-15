"""P1/P2 backend BDD evidence. Every test uses authority -> outbox -> projection."""
from __future__ import annotations

import hashlib
import os
import unittest
from datetime import datetime, timezone

from kb_pipeline.domain import ACL
from kb_pipeline.phase4_core import (BarrierState, EnvelopeOperation, PostgresFTSQueryService,
    PostgresProjectionBarrier, PostgresProjectionWorker, ReplayEnvelope, verify_citation)
from kb_pipeline.postgres_authority import MigrationRunner, PostgresAuthorityRepository
from kb_pipeline.protocol import CanonicalChange, IdentityNamespace, Operation, PermissionState, ProvenanceLink, RevisionOutcome
from kb_pipeline.security import AuthorizationError, Principal

DSN = os.getenv("P3_POSTGRES_DSN")


@unittest.skipUnless(DSN, "P3_POSTGRES_DSN not set")
class BackendBDDPostgres(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import psycopg
        cls.db = psycopg.connect(DSN)
        cls.repo = PostgresAuthorityRepository(DSN)
        cls.repo.open()
        with cls.db.transaction(): MigrationRunner().run(cls.db)

    @classmethod
    def tearDownClass(cls):
        cls.db.close(); cls.repo.close()

    def setUp(self):
        self.db.commit()
        with self.db.transaction():
            self.db.execute("TRUNCATE p4_document,p4_projection_checkpoints,p4_identity_aliases,ingestion_gaps,ingestion_authority,ingestion_outbox,ingestion_idempotency,ingestion_dead_letters,ingestion_audit RESTART IDENTITY")

    def change(self, revision=1, operation=Operation.UPSERT, text="alpha searchable", idem=None):
        source = IdentityNamespace("p4", "tenant-a", "subject", "docs", "local")
        return CanonicalChange("doc-1", source, revision, operation,
            None if operation is Operation.DELETE else {"title": "doc-1", "text": text},
            idem or f"bdd-{revision}-{operation.value}", ProvenanceLink("raw", "s3://raw/tenant-a/doc-1"),
            PermissionState(ACL(frozenset({"alice"}), frozenset())))

    def flow(self, change):
        text = (change.value or {}).get("text", "")
        outcome, sequence = self.repo.accept_with_sequence(change, raw_object_uri="s3://raw/tenant-a/doc-1",
            content_hash=hashlib.sha256(text.encode()).hexdigest())
        self.assertEqual(RevisionOutcome.ACCEPTED, outcome)
        self.db.commit()
        claimed = self.repo.claim_outbox("bdd", tenant="tenant-a", workload="docs")[0]
        envelope = ReplayEnvelope.deserialize(claimed["envelope"])
        with self.db.transaction(): PostgresProjectionWorker(self.db).apply_at_sequence(sequence, envelope)
        self.repo.mark_outbox_applied(sequence, "bdd", tenant="tenant-a", workload="docs", lease_token=claimed["lease_token"])
        return sequence, envelope

    def test_e2e001_authority_commit_outbox_projection_barrier_query(self):
        seq, _ = self.flow(self.change())
        barrier = PostgresProjectionBarrier(self.db)
        self.assertEqual(BarrierState.FRESH, barrier.observe(seq).state)
        result = PostgresFTSQueryService(self.db).search(Principal("alice", "tenant-a", source_scopes=frozenset({"docs"})), "searchable", source="docs", min_sequence=seq)
        self.assertEqual(("tenant-a", "docs", "doc-1"), result[0].identity.key)

    def test_e2e002_duplicate_same_revision_conflict_full_identity_tuple(self):
        first = self.change()
        self.assertEqual(RevisionOutcome.ACCEPTED, self.repo.accept(first, raw_object_uri="s3://raw/tenant-a/doc-1", content_hash="h"))
        self.assertEqual(RevisionOutcome.DUPLICATE, self.repo.accept(first, raw_object_uri="s3://raw/tenant-a/doc-1", content_hash="h"))
        self.assertEqual(RevisionOutcome.CONFLICT, self.repo.accept(self.change(text="other", idem="different"), raw_object_uri="s3://raw/tenant-a/doc-1", content_hash="x"))
        self.assertEqual(("p4", "tenant-a", "docs", "local", "doc-1"), tuple(self.db.execute("SELECT provider,tenant,connector,source_instance,object_id FROM ingestion_authority").fetchone()))

    def test_e2e003_gap_quarantine_recovery(self):
        self.assertEqual(RevisionOutcome.GAP, self.repo.accept(self.change(2), raw_object_uri="u", content_hash="h"))
        self.assertEqual((1, 2), tuple(self.db.execute("SELECT expected_revision,received_revision FROM ingestion_gaps").fetchone()))
        self.assertEqual(RevisionOutcome.ACCEPTED, self.repo.accept(self.change(1), raw_object_uri="u", content_hash="h"))
        self.assertEqual(RevisionOutcome.ACCEPTED, self.repo.accept(self.change(2), raw_object_uri="u", content_hash="h"))

    def test_e2e004_delete_no_resurrection(self):
        self.flow(self.change()); self.flow(self.change(2, Operation.DELETE))
        self.assertEqual(RevisionOutcome.STALE, self.repo.accept(self.change(3, text="resurrect"), raw_object_uri="u", content_hash="h"))
        self.assertEqual((2, True), tuple(self.db.execute("SELECT revision,tombstoned FROM p4_document").fetchone()))

    def test_e2e005_source_scope_and_full_identity_rejection(self):
        self.flow(self.change())
        with self.assertRaises(AuthorizationError): PostgresFTSQueryService(self.db).search(Principal("alice", "tenant-a"), "alpha", source="docs")
        self.assertEqual((), PostgresFTSQueryService(self.db).search(Principal("alice", "tenant-b", source_scopes=frozenset({"docs"})), "alpha", source="docs"))

    def test_e2e006_citation_tombstone_source_scope_rejection(self):
        seq, _ = self.flow(self.change()); p = Principal("alice", "tenant-a", source_scopes=frozenset({"docs"}))
        result = PostgresFTSQueryService(self.db).search(p, "searchable", source="docs", min_sequence=seq)[0]
        self.assertFalse(verify_citation(self.db, Principal("alice", "tenant-a", source_scopes=frozenset({"mail"})), result))
        self.flow(self.change(2, Operation.DELETE))
        self.assertFalse(verify_citation(self.db, p, result))

    def test_p4011_dlq_replay_authorized_vs_unauthorized_principal(self):
        change = self.change(); _, sequence = self.repo.accept_with_sequence(change, raw_object_uri="u", content_hash="h")
        self.db.commit(); claim = self.repo.claim_outbox("bdd", tenant="tenant-a", workload="docs")[0]
        self.repo.mark_outbox_failed(sequence, "injected", "bdd", tenant="tenant-a", workload="docs", lease_token=claim["lease_token"], max_attempts=1, base_delay_seconds=0, jitter_seconds=0)
        with self.assertRaises(PermissionError): self.repo.retry_dead_letter(sequence, operator=Principal("reader", "tenant-a", roles=frozenset({"reader"})))
        self.repo.retry_dead_letter(sequence, operator=Principal("oncall", "tenant-a", roles=frozenset({"admin"})))
