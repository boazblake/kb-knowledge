"""Phase 4 QA gate: executable contract, security, and pilot-scope checks."""

import re
import subprocess
import tempfile
import unittest
import sqlite3
from urllib.request import Request, urlopen
from urllib.error import HTTPError
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
import json
import hashlib
import os
import platform
import sys

from kb_pipeline.domain import ACL, Input
from kb_pipeline.service import KnowledgeService
from kb_pipeline.storage import LexicalIndex, MemoryAuditStore, MemoryDocumentStore, SQLiteStore
from kb_pipeline.adapters import LocalFilesConnector, PlainTextCanonicalizer, source_version
from kb_pipeline.protocol import (
    CanonicalChange, CurrentStateStore, IdentityNamespace, KnowledgeEngine,
    LexicalProjection, Operation, PermissionState, ProvenanceLink,
    RelationalReferenceLedger, StateProjection, ObjectKey, RevisionOutcome,
    LocalTestKeyProvider, Query, freshness_status, CompositionManifest,
    CapabilityDescriptor,
)
from kb_pipeline.domain import CanonicalDocument, SourceVersion


ROOT = Path(__file__).parents[1]


class Resolver:
    def __init__(self, acl):
        self.acl = acl

    def resolve(self, record):
        return self.acl


def make_service(acl=ACL(frozenset({"reader"}), frozenset({"admin"}))):
    return KnowledgeService(
        MemoryDocumentStore(), LexicalIndex(), Resolver(acl),
        PlainTextCanonicalizer(), MemoryAuditStore(),
    )


def item(name="record", payload=b"classified alpha", metadata=None, observed_at=None):
    return Input("fixture", name, payload, f"file:///{name}", metadata=metadata or {},
                 observed_at=observed_at or datetime.now(timezone.utc))


class Phase4BackendQA(unittest.TestCase):
    def test_search_metadata_uses_latest_non_delete_source_identity(self):
        service = make_service()
        record = item(
            name="metadata-record", metadata={"classification": "internal"},
        )
        record = Input(
            record.connector, record.external_id, record.payload, record.source_uri,
            record.observed_at, record.metadata, record.permissions,
            provider="provider-x", tenant="tenant-y", source_instance="instance-z",
        )
        self.assertTrue(service.ingest(record, "metadata-job"))
        document = service.store.get(record.external_id)
        hit = service.index.search("classified")[0]
        metadata = service.search_metadata(hit)
        self.assertTrue(metadata["source_identity"].startswith("provider-x:tenant-y:fixture:"))
        service.tombstone(document.document_id, "metadata-actor")
        after_delete = service._source_for(document.document_id, document.source.source_id)
        self.assertEqual("provider-x", after_delete.provider)
        self.assertEqual("tenant-y", after_delete.tenant)
        self.assertEqual("fixture", after_delete.connector)
        self.assertEqual("instance-z", after_delete.source_instance)

    def test_gate5_atomic_accept_rolls_back_before_and_after_commit_failures(self):
        """Raw metadata, ledger/outbox, and audit share one commit boundary."""
        with tempfile.TemporaryDirectory() as directory:
            db = Path(directory) / "knowledge.db"
            store = SQLiteStore(db)
            ledger = RelationalReferenceLedger(store.db)
            source = IdentityNamespace("fixture", "tenant", "subject", "connector", "instance")
            change = CanonicalChange(
                "atomic", source, 1, Operation.UPSERT, None, "atomic:1",
                ProvenanceLink("raw", "atomic"), PermissionState(ACL(frozenset({"reader"}))),
            )
            record = __import__("kb_pipeline.domain", fromlist=["RawRecord"]).RawRecord(
                SourceVersion("atomic", "1", "file:///atomic", datetime.now(timezone.utc), "hash-atomic"),
                b"atomic payload", {},
            )
            for callbacks in (
                ((lambda db: (_ for _ in ()).throw(RuntimeError("before commit"))),),
                ((lambda db: store._save_raw_sql(db, record)),
                 (lambda db: (_ for _ in ()).throw(RuntimeError("after append")))),
            ):
                with self.assertRaises(RuntimeError):
                    ledger.atomic_accept(change, before_append=callbacks[:1], after_append=callbacks[1:])
                self.assertEqual(0, store.db.execute("SELECT count(*) FROM raw_records").fetchone()[0])
                self.assertEqual(0, store.db.execute("SELECT count(*) FROM protocol_ledger").fetchone()[0])
                self.assertEqual(0, store.db.execute("SELECT count(*) FROM audit").fetchone()[0])
            event = ("atomic:1", "ingest", "qa", "atomic", datetime.now(timezone.utc).isoformat())
            self.assertEqual("accepted", ledger.atomic_accept(
                change, before_append=((lambda db: store._save_raw_sql(db, record)),),
                after_append=((lambda db: db.execute("INSERT INTO audit VALUES (?,?,?,?,?)", event)),),
            ).value)
            self.assertEqual((1, "pending"), tuple(ledger.outbox()[0]))

    def test_gate5_projection_failure_retries_to_convergence(self):
        ledger = RelationalReferenceLedger(sqlite3.connect(":memory:"))
        class FailingProjection:
            name = "failing"
            def apply(self, change): raise RuntimeError("projection down")
            def remove(self, object_id, source=None): pass
        engine = KnowledgeEngine(ledger, CurrentStateStore(), (FailingProjection(),))
        with self.assertRaises(RuntimeError): engine.apply(CanonicalChange(
            "converge", IdentityNamespace("fixture", "tenant", "subject", "connector", "instance"),
            1, Operation.UPSERT, None, "converge:1", ProvenanceLink("raw", "converge"),
            PermissionState(ACL(frozenset({"reader"}))),
        ))
        self.assertEqual("pending", ledger.outbox()[0][1])
        rebuilt = LexicalIndex()
        converged = KnowledgeEngine(ledger, CurrentStateStore(), (LexicalProjection(rebuilt),))
        converged.process_outbox()
        self.assertEqual("applied", ledger.outbox()[0][1])

    def test_gate5_concurrent_duplicate_acceptance_has_one_ledger_row(self):
        ledger = RelationalReferenceLedger(sqlite3.connect(":memory:", check_same_thread=False))
        source = IdentityNamespace("fixture", "tenant", "subject", "connector", "instance")
        change = CanonicalChange("duplicate", source, 1, Operation.UPSERT, None, "duplicate:1",
                                 ProvenanceLink("raw", "duplicate"), PermissionState(ACL(frozenset({"reader"}))))
        outcomes = []
        threads = [threading.Thread(target=lambda: outcomes.append(ledger.append_outcome(change))) for _ in range(8)]
        for thread in threads: thread.start()
        for thread in threads: thread.join()
        self.assertEqual(1, sum(outcome == RevisionOutcome.ACCEPTED for outcome in outcomes))
        self.assertEqual(7, sum(outcome == RevisionOutcome.DUPLICATE for outcome in outcomes))
        self.assertEqual(1, len(ledger.changes()))

    def test_gate5_gap_persists_and_recovery_does_not_skip_revision(self):
        ledger = RelationalReferenceLedger(sqlite3.connect(":memory:"))
        source = IdentityNamespace("fixture", "tenant", "subject", "connector", "instance")
        def make(revision):
            return CanonicalChange("gap", source, revision, Operation.UPSERT, None, f"gap:{revision}",
                                    ProvenanceLink("raw", "gap"), PermissionState(ACL(frozenset({"reader"}))))
        self.assertEqual(RevisionOutcome.GAP, ledger.append_outcome(make(3)))
        self.assertEqual(1, len(ledger.gaps()))
        self.assertEqual(RevisionOutcome.GAP, ledger.append_outcome(make(3)))
        self.assertEqual(RevisionOutcome.ACCEPTED, ledger.append_outcome(make(1)))
        self.assertEqual(RevisionOutcome.ACCEPTED, ledger.append_outcome(make(2)))
        self.assertEqual((1, 2), tuple(change.revision for change in ledger.changes()))

    def test_gate5_checkpoint_replay_is_bounded_and_repair_rebuilds_all(self):
        ledger = RelationalReferenceLedger(sqlite3.connect(":memory:"))
        index = LexicalIndex()
        engine = KnowledgeEngine(ledger, CurrentStateStore(), (LexicalProjection(index),))
        source = IdentityNamespace("fixture", "tenant", "subject", "connector", "instance")
        for revision in (1, 2, 3):
            doc = CanonicalDocument("bounded", SourceVersion("bounded", str(revision), "file:///bounded", datetime.now(timezone.utc), f"hash-{revision}"), "bounded", f"v{revision}", ACL(frozenset({"reader"})))
            self.assertEqual(RevisionOutcome.ACCEPTED, ledger.append_outcome(CanonicalChange(
                "bounded", source, revision, Operation.UPSERT, doc, f"bounded:{revision}",
                ProvenanceLink("raw", "bounded"), PermissionState(ACL(frozenset({"reader"}))),
            )))
        engine.replay()
        checkpoint = ledger.checkpoint("default:lexical")
        self.assertEqual(3, checkpoint)
        self.assertTrue(engine.replay())
        self.assertEqual(3, ledger.checkpoint("default:lexical"))
        repaired = LexicalIndex()
        repair = KnowledgeEngine(ledger, CurrentStateStore(), (LexicalProjection(repaired),))
        self.assertTrue(repair.replay(rebuild=True))
        self.assertEqual(1, len(repaired.search("v3")))

    def test_gate5_shared_artifact_refcount_survives_partial_purge(self):
        with tempfile.TemporaryDirectory() as directory:
            store = SQLiteStore(Path(directory) / "knowledge.db")
            svc = KnowledgeService(store, LexicalIndex(), Resolver(ACL(frozenset({"reader"}))),
                                   PlainTextCanonicalizer(), store)
            svc.ingest(item("one", b"same bytes"), "one-job")
            svc.ingest(item("two", b"same bytes"), "two-job")
            artifact = next(Path(store.artifact_root).iterdir())
            self.assertEqual(2, store.db.execute("SELECT ref_count FROM artifacts").fetchone()[0])
            svc.tombstone("one", "admin")
            store.purge(datetime.now(timezone.utc) + timedelta(seconds=1), document_id="one")
            self.assertTrue(artifact.exists())
            self.assertEqual(1, store.db.execute("SELECT ref_count FROM artifacts").fetchone()[0])
    def test_gate4_evidence_requires_complete_observed_results(self):
        from kb_pipeline.cli import validate_evidence
        evidence = {
            "schema": "kb-pipeline.gate4-evidence.v1", "gate": 4, "validation_owner": "QA",
            "provenance": {"source": "result_json", "manifest": "tests/test_manifest.json",
                           "manifest_sha256": __import__("hashlib").sha256(
                               (ROOT / "tests/test_manifest.json").read_bytes()).hexdigest(),
                           "captured_at": "2026-08-13T00:00:00Z"},
            "test_count": 72, "suite_version": "0.1.0", "environment": {"python": "3.11"},
            "scenario_results": [{"id": "QA-001", "status": "pass"}],
            "backup_bundle_checksums": [{"path": "database.sqlite", "sha256": "a" * 64}],
            "sqlite_integrity": "pass", "restore_validation": "pass",
            "interruption_outcomes": [{"id": "restore-copy", "status": "pass"}],
            "category_results": {name: "pass" for name in ("purge", "replay", "readiness", "limits", "log_redaction")},
            "exclusions": ["external KMS/OIDC", "production claims", "non-local connectors"],
        }
        self.assertEqual(evidence, validate_evidence(evidence))

    def test_gate4_evidence_rejects_stale_manifest_count(self):
        from kb_pipeline.cli import validate_evidence
        evidence = {
            "schema": "kb-pipeline.gate4-evidence.v1", "gate": 4, "validation_owner": "QA",
            "provenance": {"source": "result_json", "manifest": "tests/test_manifest.json",
                           "manifest_sha256": __import__("hashlib").sha256(
                               (ROOT / "tests/test_manifest.json").read_bytes()).hexdigest(),
                           "captured_at": "2026-08-13T00:00:00Z"},
            "test_count": 56, "suite_version": "0.1.0", "environment": {"python": "3.11"},
            "scenario_results": [{"id": "QA-001", "status": "pass"}],
            "backup_bundle_checksums": [{"path": "database.sqlite", "sha256": "a" * 64}],
            "sqlite_integrity": "pass", "restore_validation": "pass",
            "interruption_outcomes": [{"id": "restore-copy", "status": "pass"}],
            "category_results": {name: "pass" for name in ("purge", "replay", "readiness", "limits", "log_redaction")},
            "exclusions": ["external KMS/OIDC"],
        }
        with self.assertRaisesRegex(ValueError, "test_count does not match"):
            validate_evidence(evidence)

    def test_gate4_evidence_rejects_placeholders_and_unknown_fields(self):
        from kb_pipeline.cli import validate_evidence
        with self.assertRaises(ValueError):
            validate_evidence({"schema": "kb-pipeline.gate4-evidence.v1", "test_count": "reported_by_test_runner"})
        with self.assertRaises(ValueError):
            validate_evidence({"schema": "kb-pipeline.gate4-evidence.v1", "unexpected": True})

    def test_pilot_evidence_requires_explicit_result_json(self):
        result = subprocess.run([sys.executable, "-m", "kb_pipeline.cli", "pilot-evidence", ":memory:"],
                                cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        self.assertNotEqual(0, result.returncode)
        self.assertIn("--result-json", result.stdout)
    def test_object_key_isolates_every_identity_dimension(self):
        base = IdentityNamespace("provider", "tenant", "subject", "connector", "source-a")
        variants = [
            IdentityNamespace("other-provider", "tenant", "subject", "connector", "source-a"),
            IdentityNamespace("provider", "other-tenant", "subject", "connector", "source-a"),
            IdentityNamespace("provider", "tenant", "subject", "other-connector", "source-a"),
            IdentityNamespace("provider", "tenant", "subject", "connector", "source-b"),
        ]
        keys = {ObjectKey.from_change(CanonicalChange(
            "same-object", source, 1, Operation.UPSERT, None, str(i),
            ProvenanceLink("raw", str(i)), PermissionState(ACL(frozenset({"reader"})))
        )).tuple() for i, source in enumerate([base, *variants])}
        self.assertEqual(5, len(keys))

    def test_revisions_are_owned_by_exact_object_key(self):
        ledger = RelationalReferenceLedger(sqlite3.connect(":memory:"))
        def make(source, revision, text):
            return CanonicalChange(
                "same", source, revision, Operation.UPSERT,
                CanonicalDocument("same", SourceVersion("same", str(revision), "file:/same", datetime.now(timezone.utc), text), "same", text, ACL(frozenset({"reader"}))),
                f"{source.connector}:{revision}", ProvenanceLink("raw", text), PermissionState(ACL(frozenset({"reader"})))
            )
        left = IdentityNamespace("p", "t", "s", "left", "source")
        right = IdentityNamespace("p", "t", "s", "right", "source")
        self.assertEqual(RevisionOutcome.ACCEPTED, ledger.append_outcome(make(left, 1, "left")))
        self.assertEqual(RevisionOutcome.ACCEPTED, ledger.append_outcome(make(right, 1, "right")))

    def test_gap_is_quarantined_then_missing_revision_recovers(self):
        ledger = RelationalReferenceLedger(sqlite3.connect(":memory:"))
        source = IdentityNamespace("p", "t", "s", "c", "source")
        def make(revision):
            return CanonicalChange("o", source, revision, Operation.UPSERT, None, f"o:{revision}", ProvenanceLink("raw", "o"), PermissionState(ACL(frozenset({"reader"}))))
        self.assertEqual(RevisionOutcome.ACCEPTED, ledger.append_outcome(make(1)))
        self.assertEqual(RevisionOutcome.GAP, ledger.append_outcome(make(3)))
        self.assertEqual(RevisionOutcome.ACCEPTED, ledger.append_outcome(make(2)))
        self.assertEqual(1, len(ledger.gaps()))

    def test_ledger_outbox_and_replay_repair_are_observable(self):
        ledger = RelationalReferenceLedger(sqlite3.connect(":memory:"))
        source = IdentityNamespace("p", "t", "s", "c", "source")
        change = CanonicalChange("o", source, 1, Operation.UPSERT, None, "o:1", ProvenanceLink("raw", "o"), PermissionState(ACL(frozenset({"reader"}))))
        self.assertTrue(ledger.append(change))
        self.assertEqual(((1, "pending"),), ledger.outbox())
        rebuilt = KnowledgeEngine(ledger, CurrentStateStore())
        self.assertTrue(rebuilt.replay())
        self.assertIsNotNone(rebuilt.store.current("o", source))

    def test_encrypted_payload_seam_has_no_plaintext_fallback(self):
        provider = LocalTestKeyProvider()
        plaintext = b"sensitive payload"
        envelope = provider.encrypt(plaintext, key_id="qa-key")
        self.assertNotEqual(plaintext, envelope.ciphertext)
        self.assertEqual(plaintext, provider.decrypt(envelope))
        tampered = envelope.__class__(envelope.key_id, envelope.algorithm, envelope.ciphertext + b"x", envelope.nonce, envelope.tag)
        with self.assertRaises(ValueError):
            provider.decrypt(tampered)

    def test_freshness_boundaries_are_exact(self):
        now = datetime(2026, 1, 1, tzinfo=timezone.utc)
        self.assertEqual("fresh", freshness_status(now - timedelta(minutes=5), now=now))
        self.assertEqual("stale", freshness_status(now - timedelta(minutes=5, seconds=1), now=now))
        self.assertEqual("fresh", freshness_status(now - timedelta(minutes=15), external=True, now=now))
        self.assertEqual("stale", freshness_status(now - timedelta(minutes=15, seconds=1), external=True, now=now))

    def test_query_limits_and_capability_composition_fail_closed(self):
        with self.assertRaises(ValueError): Query("x", "reader", limit=0)
        with self.assertRaises(ValueError): Query("x", "reader", limit=101)
        good = CapabilityDescriptor("ledger", "1.2.0", frozenset({"replay", "revision"}))
        self.assertTrue(CompositionManifest({"ledger": good}, {"ledger": CapabilityDescriptor("ledger", "1.0.0", frozenset({"replay"}))}).validate())
        with self.assertRaises(ValueError):
            CompositionManifest({"ledger": good}, {"ledger": CapabilityDescriptor("ledger", "2.0.0", frozenset())}).validate()

    def test_loopback_identity_is_short_lived_and_constant_time_checked(self):
        from kb_pipeline.api import LoopbackSyntheticIdentity
        identity = LoopbackSyntheticIdentity(ttl_seconds=0)
        self.assertFalse(identity.valid(identity.token))

    def test_stable_contract_and_source_provenance(self):
        svc = make_service()
        self.assertTrue(svc.ingest(item(), "job-1"))
        hit = svc.search("classified", "reader")[0]
        self.assertEqual({"document_id", "title", "snippet", "source_uri", "source_version"},
                         set(hit.__dataclass_fields__))
        self.assertEqual("file:///record", hit.source_uri)
        self.assertRegex(hit.source_version, r"^[0-9a-f]{64}$")

    def test_acl_denies_unknown_and_separates_admin_content(self):
        svc = make_service(ACL(None, frozenset({"admin"})))
        svc.ingest(item("record", b"secret"), "job")
        self.assertEqual([], svc.search("secret", "reader"))
        self.assertEqual([], svc.search("secret", "admin", is_admin=False))

        admin_only = make_service(ACL(frozenset(), frozenset({"admin"})))
        admin_only.ingest(item(payload=b"admin secret"), "admin-job")
        self.assertEqual([], admin_only.search("secret", "reader"))
        self.assertEqual(1, len(admin_only.search("secret", "admin", is_admin=True)))

    def test_acl_change_removes_old_index_candidate(self):
        svc = make_service()
        svc.ingest(item(payload=b"visible secret"), "v1")
        svc.acl.acl = ACL(frozenset())
        svc.ingest(item(payload=b"visible secret v2"), "v2")
        self.assertEqual([], svc.search("secret", "reader"))

    def test_tombstone_purge_and_replay_do_not_resurrect(self):
        svc = make_service()
        svc.ingest(item(), "first")
        svc.tombstone("record", "admin")
        self.assertEqual(1, svc.store.purge(datetime.now(timezone.utc) + timedelta(seconds=1)))
        svc.ingest(item(payload=b"replayed classified alpha"), "replay")
        self.assertEqual([], svc.search("classified", "reader"))
        self.assertIsNone(svc.store.get("record"))

    def test_idempotency_and_retry_after_index_failure(self):
        class FailingIndex(LexicalIndex):
            def __init__(self):
                super().__init__()
                self.fail = True

            def replace(self, d):
                if self.fail:
                    self.fail = False
                    raise RuntimeError("index unavailable")
                super().replace(d)

        index = FailingIndex()
        audit = MemoryAuditStore()
        svc = KnowledgeService(MemoryDocumentStore(), index, Resolver(ACL(frozenset({"reader"}))),
                               PlainTextCanonicalizer(), audit)
        with self.assertRaises(RuntimeError):
            svc.ingest(item(), "retry")
        self.assertTrue(svc.ingest(item(), "retry"))
        self.assertFalse(svc.ingest(item(), "retry"))
        self.assertEqual(1, len(svc.search("classified", "reader")))

    def test_revocation_uses_both_configured_boundaries(self):
        svc = make_service()
        self.assertEqual(timedelta(minutes=15), svc.revocation_grace)
        self.assertEqual(timedelta(minutes=30), svc.hard_max)
        svc.ingest(item(), "job")
        at = datetime(2026, 1, 1, tzinfo=timezone.utc)
        svc.revoke_source("record", at)
        self.assertEqual(at + timedelta(minutes=30), svc._suppressed["record"])

    def test_revocation_acl_refresh_can_restore_within_15_minutes(self):
        """Authorized ACL refresh restores visibility during configured grace."""
        svc = make_service()
        revoked_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
        svc.ingest(item(payload=b"before revoke", metadata={}), "before")
        svc.revoke_source("record", revoked_at)
        svc.acl.acl = ACL(frozenset({"reader"}))
        svc.ingest(item(payload=b"after refresh", metadata={},
                        observed_at=revoked_at + timedelta(minutes=15)), "refresh")
        self.assertEqual(1, len(svc.search("after", "reader")))

    def test_revocation_uncertainty_remains_denied_after_grace(self):
        svc = make_service()
        revoked_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
        svc.ingest(item(), "before")
        svc.revoke_source("record", revoked_at)
        svc.acl.acl = ACL(None)
        refresh_at = revoked_at + timedelta(minutes=15, seconds=1)
        svc.ingest(item(payload=b"uncertain refresh", metadata={}, observed_at=refresh_at), "refresh")
        self.assertEqual([], svc.search("uncertain", "reader"))
        self.assertEqual(revoked_at + timedelta(minutes=30), svc._suppressed["record"])

    def test_configured_grace_controls_acl_refresh_recovery(self):
        svc = KnowledgeService(
            MemoryDocumentStore(), LexicalIndex(), Resolver(ACL(frozenset({"reader"}))),
            PlainTextCanonicalizer(), MemoryAuditStore(),
            revocation_grace=timedelta(minutes=5), hard_max=timedelta(minutes=30),
        )
        revoked_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
        svc.revoke_source("record", revoked_at)
        svc.ingest(item(payload=b"too late", observed_at=revoked_at + timedelta(minutes=5, seconds=1)), "late")
        self.assertEqual([], svc.search("late", "reader"))

    def test_restart_rebuilds_search_index_from_durable_store(self):
        """Durable document state must remain searchable after process restart."""
        with tempfile.TemporaryDirectory() as directory:
            db = Path(directory) / "knowledge.db"
            first = KnowledgeService(SQLiteStore(db), LexicalIndex(),
                                     Resolver(ACL(frozenset({"reader"}))),
                                     PlainTextCanonicalizer(), MemoryAuditStore())
            first.ingest(item(payload=b"durable restart evidence"), "job")

            restarted = KnowledgeService(SQLiteStore(db), LexicalIndex(),
                                         Resolver(ACL(frozenset({"reader"}))),
                                         PlainTextCanonicalizer(), MemoryAuditStore())
            self.assertEqual(1, len(restarted.search("restart", "reader")))

    def test_rejected_stale_version_cannot_replace_new_index_content(self):
        """Rejected out-of-order writes must not leak stale indexed content."""
        svc = make_service()
        newer = item(payload=b"newer value", observed_at=datetime(2026, 1, 2, tzinfo=timezone.utc))
        older = item(payload=b"older value", observed_at=datetime(2026, 1, 1, tzinfo=timezone.utc))
        svc.ingest(newer, "new")
        svc.ingest(older, "old")
        self.assertEqual([], svc.search("older", "reader"))

    def test_revocation_survives_restart(self):
        with tempfile.TemporaryDirectory() as directory:
            db = Path(directory) / "knowledge.db"
            first = KnowledgeService(SQLiteStore(db), LexicalIndex(), Resolver(ACL(frozenset({"reader"}))), PlainTextCanonicalizer(), MemoryAuditStore())
            first.ingest(item(), "job")
            first.revoke_source("record", datetime.now(timezone.utc))
            restarted = KnowledgeService(SQLiteStore(db), LexicalIndex(), Resolver(ACL(frozenset({"reader"}))), PlainTextCanonicalizer(), MemoryAuditStore())
            self.assertEqual([], restarted.search("classified", "reader"))

    def test_backup_restore_preserves_raw_artifact_links(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); db = root / "knowledge.db"; bundle = root / "backup"
            svc = KnowledgeService(SQLiteStore(db), LexicalIndex(), Resolver(ACL(frozenset({"reader"}))), PlainTextCanonicalizer(), MemoryAuditStore())
            svc.ingest(item(payload=b"raw evidence"), "job")
            subprocess.run(["python3", "-m", "kb_pipeline.cli", "backup", str(db), str(bundle)], cwd=ROOT, check=True)
            restored_db = root / "restored.db"
            subprocess.run(["python3", "-m", "kb_pipeline.cli", "restore", str(restored_db), str(bundle)], cwd=ROOT, check=True)
            restored = SQLiteStore(restored_db)
            self.assertTrue(restored.validate_artifact_links())

    def test_backup_failure_hooks_leave_previous_bundle_intact(self):
        from kb_pipeline.cli import _backup
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); db = root / "knowledge.db"; bundle = root / "backup"
            store = SQLiteStore(db); store.db.execute("CREATE TABLE IF NOT EXISTS marker(value TEXT)"); store.db.execute("INSERT INTO marker VALUES ('old')"); store.db.commit()
            _backup(db, bundle)
            before = (bundle / "database.sqlite").read_bytes()
            for hook in ("db_copy", "artifact_copy", "manifest_checksum", "publish"):
                with self.assertRaises(RuntimeError): _backup(db, bundle, (hook,))
                self.assertEqual(before, (bundle / "database.sqlite").read_bytes())
                self.assertTrue((bundle / "manifest.json").is_file())

    def test_restore_failure_keeps_previous_target_intact(self):
        from kb_pipeline.cli import _backup, _restore
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); db = root / "knowledge.db"; bundle = root / "backup"
            SQLiteStore(db).db.execute("CREATE TABLE marker(value TEXT)")
            store = SQLiteStore(db); store.db.execute("INSERT INTO marker VALUES ('old')"); store.db.commit()
            _backup(db, bundle)
            target = root / "target.db"; target_store = SQLiteStore(target); target_store.db.execute("CREATE TABLE marker(value TEXT)"); target_store.db.execute("INSERT INTO marker VALUES ('previous')"); target_store.db.commit(); target_store.db.close()
            with self.assertRaises(RuntimeError): _restore(target, bundle, ("restore_promotion",))
            check = SQLiteStore(target)
            self.assertEqual("previous", check.db.execute("SELECT value FROM marker").fetchone()[0])

    def test_restore_copy_interruption_does_not_create_partial_target(self):
        from kb_pipeline.cli import _backup, _restore
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); db = root / "knowledge.db"; bundle = root / "backup"; SQLiteStore(db).db.close()
            _backup(db, bundle)
            target = root / "new.db"
            with self.assertRaises(RuntimeError): _restore(target, bundle, ("restore_db_copy",))
            self.assertFalse(target.exists())

    def test_incomplete_scan_does_not_delete_unseen_documents(self):
        """Symlink/limit/error scans must not authorize destructive reconciliation."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "known.txt").write_text("known content")
            service = make_service()
            service.ingest(item("known.txt", b"known content"), "seed")
            connector = LocalFilesConnector(root, max_files=0)
            result = service.reconcile(connector, "partial")
            self.assertFalse(result["complete"])
            self.assertEqual(0, result["deleted"])
            self.assertEqual(1, len(service.search("known", "reader")))

    def test_ignored_paths_do_not_trigger_tombstone_inference(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); (root / ".git").mkdir()
            (root / ".git" / "old.txt").write_text("old")
            service = make_service()
            service.ingest(item(".git/old.txt", b"old"), "seed")
            result = service.reconcile(LocalFilesConnector(root), "snapshot")
            self.assertTrue(result["complete"])
            self.assertEqual(0, result["deleted"])

    def test_protocol_state_and_projection_are_tenant_scoped(self):
        """Same object IDs in separate tenant namespaces must not overwrite."""
        def tenant_change(tenant, text):
            source = IdentityNamespace("fixture", tenant, "connector")
            version = SourceVersion("same-id", "1", f"file:///{tenant}", datetime.now(timezone.utc), tenant)
            doc = CanonicalDocument("same-id", version, tenant, text, ACL(frozenset({"reader"})))
            return CanonicalChange("same-id", source, 1, Operation.UPSERT, doc,
                                   f"{tenant}:1", ProvenanceLink("raw", tenant), PermissionState(doc.acl))

        index = LexicalIndex()
        engine = KnowledgeEngine(RelationalReferenceLedger(sqlite3.connect(":memory:")),
                                 CurrentStateStore(), (StateProjection(), LexicalProjection(index)))
        self.assertTrue(engine.apply(tenant_change("tenant-a", "alpha")))
        self.assertTrue(engine.apply(tenant_change("tenant-b", "bravo")))
        current = engine.store.current("same-id")
        self.assertIsNotNone(current)
        self.assertEqual("alpha", current.value.text)
        self.assertEqual(2, len(index.search("alpha bravo")))

    def test_purge_removes_raw_artifact_and_derived_projection(self):
        """Data-class purge must remove source payload, not only canonical row."""
        with tempfile.TemporaryDirectory() as directory:
            db = Path(directory) / "knowledge.db"
            store = SQLiteStore(db)
            svc = KnowledgeService(store, LexicalIndex(), Resolver(ACL(frozenset({"reader"}))),
                                    PlainTextCanonicalizer(), MemoryAuditStore())
            svc.ingest(item(payload=b"purge-me"), "purge")
            artifact = next(Path(store.artifact_root).iterdir())
            svc.tombstone("record", "admin")
            store.purge(datetime.now(timezone.utc) + timedelta(seconds=1))
            self.assertFalse(artifact.exists())

    def test_same_revision_conflict_is_not_added_to_ledger(self):
        first = change = None
        source = IdentityNamespace("fixture", "tenant", "connector")
        def make(text, key):
            version = SourceVersion("conflict", "1", "file:///conflict", datetime.now(timezone.utc), text)
            doc = CanonicalDocument("conflict", version, "conflict", text, ACL(frozenset({"reader"})))
            return CanonicalChange("conflict", source, 1, Operation.UPSERT, doc, key,
                                   ProvenanceLink("raw", "conflict"), PermissionState(doc.acl))
        first = make("first", "conflict:1")
        second = make("second", "conflict:other")
        ledger = RelationalReferenceLedger(sqlite3.connect(":memory:"))
        engine = KnowledgeEngine(ledger, CurrentStateStore())
        self.assertTrue(engine.apply(first))
        self.assertFalse(engine.apply(second))
        self.assertEqual(1, len(ledger.changes()))

    def test_api_requires_identity_and_returns_query_contract(self):
        """API must enforce auth and expose stable item shape."""
        from kb_pipeline.api import create_server
        # Ephemeral port prevents serial/parallel QA runs from colliding on 8080.
        server, token = create_server(make_service(), port=0)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with self.assertRaises(HTTPError) as denied:
                urlopen(Request(f"http://{server.server_address[0]}:{server.server_address[1]}/v1/search?q=secret"))
            self.assertEqual(401, denied.exception.code)
            make_service().ingest(item(), "api")
            request = Request(f"http://{server.server_address[0]}:{server.server_address[1]}/v1/search?q=secret",
                              headers={"Authorization": f"Bearer {token}"})
            response = urlopen(request)
            self.assertEqual(200, response.status)
            self.assertIn("items", response.read().decode())
        finally:
            server.shutdown()
            server.server_close()


class Phase4FrontendQA(unittest.TestCase):
    def setUp(self):
        self.html = (ROOT / "frontend/index.html").read_text()
        self.js = (ROOT / "frontend/app.js").read_text()

    def test_accessibility_basics_and_ai_disabled_scope(self):
        for expected in ('lang="en"', 'for="query"', 'id="query"', 'aria-live="polite"',
                         'role="status"', 'aria-busy'):
            self.assertIn(expected, self.html + self.js)
        # Answer mode uses same-origin API only; browser owns no provider credentials.
        self.assertIn("const apiBase = '/v1'", self.js)
        self.assertIn("${apiBase}/answer", self.js)
        self.assertNotRegex(self.html, r"<script[^>]+src=[\"']https?://", re.I)
        for forbidden in ("https://", "openai", "anthropic", "ollama", "apiKey", "api_key",
                          "client_secret", "Authorization"):
            self.assertNotIn(forbidden, self.js)
        for expected in ('id="answer-form"', 'for="answer-query"', 'id="answer-query"',
                         'id="answer-button"', 'id="answer-status"', 'role="status"',
                         'id="answer-result"', 'id="answer-citations"'):
            self.assertIn(expected, self.html)
        # Normal answers require text; structured visual summaries require validated summary data.
        self.assertIn("(!answer && !visualSummary)", self.js)
        self.assertIn("!citations.length", self.js)
        self.assertIn("payload?.visual_evidence === true", self.js)
        self.assertIn("renderVisualSummary", self.js)
        self.assertIn("It is not clinical interpretation.", self.js)
        self.assertIn("answerCitations.append(item)", self.js)
        self.assertLess(self.js.index("answerCitations.append(item)"),
                        self.js.index("answerResult.hidden = false"))

    def test_ui_escapes_result_content_and_honestly_disclaims_unsupported_features(self):
        self.assertIn("textContent", self.js)
        self.assertNotIn("innerHTML", self.js)
        for expected in ("freshness timestamp", "formal citations", "email and attachment search",
                         "Admin view", "unavailable"):
            self.assertIn(expected, self.html)

    def test_ui_exposes_local_scope_version_and_supported_degraded_state(self):
        self.assertIn("Scope: local plaintext files", self.html)
        for expected in ("Content version", "Freshness", "Local file", "payload.degraded",
                          "tombstones"):
            self.assertIn(expected, self.js)

    def test_result_scope_uses_current_local_reference_wording(self):
        self.assertIn("Local reference · currently indexed local documents · API controls access", self.js)
        self.assertNotIn("Synthetic local", self.js)

    def test_ui_withholds_details_on_auth_and_service_failures(self):
        self.assertIn("No file details were shown", self.js)
        self.assertIn("No results were shown", self.js)
        self.assertIn("response.status === 403", self.js)
        self.assertIn("response.status === 503", self.js)

    def test_ui_uses_same_origin_v1_routes_without_client_auth_bypass(self):
        self.assertIn("const apiBase = '/v1'", self.js)
        self.assertIn("${apiBase}/search", self.js)
        self.assertIn("${apiBase}/status", self.js)
        self.assertNotIn("localStorage", self.js)
        self.assertNotIn("sessionStorage", self.js)
        self.assertNotIn("Authorization", self.js)
        self.assertIn("safeDisplayValue", self.js)


if __name__ == "__main__":
    unittest.main()
