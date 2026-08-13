import sqlite3
import unittest
from datetime import datetime, timezone

from kb_pipeline.domain import ACL, CanonicalDocument, SourceVersion
from kb_pipeline.protocol import (CanonicalChange, CompositionManifest, CurrentStateStore,
    IdentityNamespace, KnowledgeEngine, LexicalProjection, Operation, PermissionState,
    ProvenanceLink, RelationalReferenceLedger, StateProjection, CapabilityDescriptor,
    ObjectKey)
from kb_pipeline.storage import LexicalIndex


def change(object_id="doc", revision=1, operation=Operation.UPSERT, text="alpha", source="fixture"):
    ns = IdentityNamespace(source, "tenant", "connector")
    sv = SourceVersion(object_id, str(revision), f"file:///{object_id}", datetime.now(timezone.utc), f"hash-{revision}")
    doc = CanonicalDocument(object_id, sv, object_id, text, ACL(frozenset({"reader"})))
    return CanonicalChange(object_id, ns, revision, operation, None if operation == Operation.DELETE else doc,
                           f"{object_id}:{revision}:{operation}", ProvenanceLink("raw", object_id), PermissionState(doc.acl))


class ProtocolTests(unittest.TestCase):
    def test_outbox_lease_retry_and_dead_letter(self):
        ledger = RelationalReferenceLedger(sqlite3.connect(":memory:"))
        self.assertTrue(ledger.append(change()))
        self.assertEqual((1,), ledger.claim_outbox("worker", lease_seconds=1))
        ledger.mark_failed(1, "worker", "boom")
        self.assertEqual("pending", ledger.outbox()[0][1])
        for _ in range(5):
            ledger.claim_outbox("worker")
            ledger.mark_failed(1, "worker", "boom")
        self.assertEqual(1, len(ledger.dead_letters()))

    def test_revision_must_be_positive(self):
        with self.assertRaises(ValueError):
            RelationalReferenceLedger(sqlite3.connect(":memory:")).append(change(revision=0))

    def test_duplicate_stale_delete_and_replay(self):
        ledger = RelationalReferenceLedger(sqlite3.connect(":memory:")); state = CurrentStateStore(); index = LexicalIndex()
        engine = KnowledgeEngine(ledger, state, (StateProjection(), LexicalProjection(index)))
        self.assertTrue(engine.apply(change()))
        self.assertFalse(engine.apply(change()))
        self.assertFalse(engine.apply(change(revision=1, text="stale")))
        self.assertTrue(engine.apply(change(revision=2, operation=Operation.DELETE)))
        self.assertFalse(engine.apply(change(revision=3, text="replay")))
        self.assertEqual([], index.search("alpha"))

    def test_crash_replay_rebuilds_projections_from_ledger(self):
        db = sqlite3.connect(":memory:"); ledger = RelationalReferenceLedger(db)
        engine = KnowledgeEngine(ledger, CurrentStateStore(), (LexicalProjection(LexicalIndex()),)); engine.apply(change())
        rebuilt_index = LexicalIndex(); rebuilt = KnowledgeEngine(ledger, CurrentStateStore(), (LexicalProjection(rebuilt_index),)); rebuilt.replay()
        self.assertEqual(1, len(rebuilt_index.search("alpha")))

    def test_permission_and_source_isolation(self):
        index = LexicalIndex(); projection = LexicalProjection(index)
        hidden = change(source="other"); hidden = CanonicalChange(hidden.object_id, hidden.source, hidden.revision, hidden.operation, hidden.value, "hidden", hidden.provenance, PermissionState(ACL(None)))
        projection.apply(hidden); self.assertEqual([], index.search("alpha"))

    def test_current_state_keeps_same_object_per_tenant(self):
        state = CurrentStateStore()
        first = change()
        second = change(text="bravo")
        first = CanonicalChange(first.object_id, IdentityNamespace("fixture", "tenant-a", "connector"),
                                first.revision, first.operation, first.value, first.idempotency_key + "-a",
                                first.provenance, first.permissions)
        second = CanonicalChange(second.object_id, IdentityNamespace("fixture", "tenant-b", "connector"),
                                 second.revision, second.operation, second.value, second.idempotency_key + "-b",
                                 second.provenance, second.permissions)
        self.assertTrue(state.apply(first))
        self.assertTrue(state.apply(second))
        self.assertIsNotNone(state.current("doc", first.source))
        self.assertIsNotNone(state.current("doc", second.source))
        first_current = state.current("doc", first.source)
        second_current = state.current("doc", second.source)
        self.assertEqual("alpha", first_current.value.text if first_current else None)
        self.assertEqual("bravo", second_current.value.text if second_current else None)

    def test_same_object_id_across_source_instances_stays_distinct(self):
        ledger = RelationalReferenceLedger(sqlite3.connect(":memory:"))
        state = CurrentStateStore()
        sources = (IdentityNamespace("p", "t", "subject", "c", "one"),
                   IdentityNamespace("p", "t", "subject", "c", "two"))
        for source, text in zip(sources, ("one", "two")):
            original = change(text=text)
            current = CanonicalChange(original.object_id, source, original.revision,
                                      original.operation, original.value,
                                      source.source_instance, original.provenance,
                                      original.permissions)
            self.assertTrue(ledger.append(current))
            self.assertTrue(state.apply(current))
        self.assertEqual("one", state.current("doc", sources[0]).value.text)
        self.assertEqual("two", state.current("doc", sources[1]).value.text)
        self.assertEqual(2, len(ledger.changes()))

    def test_replay_preserves_full_source_identity_exactly(self):
        ledger = RelationalReferenceLedger(sqlite3.connect(":memory:"))
        source = IdentityNamespace("provider", "tenant", "subject", "connector", "instance")
        original = change()
        original = CanonicalChange(original.object_id, source, original.revision,
                                   original.operation, original.value, "identity-replay",
                                   original.provenance, original.permissions)
        self.assertTrue(ledger.append(original))
        replayed = tuple(ledger.changes())[0]
        self.assertEqual(original.source, replayed.source)
        self.assertEqual(ObjectKey.from_change(original), ObjectKey.from_change(replayed))

    def test_conflicting_revision_is_quarantined_but_duplicate_delivery_is_allowed(self):
        ledger = RelationalReferenceLedger(sqlite3.connect(":memory:"))
        first = change()
        self.assertTrue(ledger.append(first))
        self.assertFalse(ledger.append(first))
        conflict = change(text="conflict")
        conflict = CanonicalChange(conflict.object_id, conflict.source, conflict.revision,
                                   conflict.operation, conflict.value, "other",
                                   conflict.provenance, conflict.permissions)
        self.assertFalse(ledger.append(conflict))
        self.assertEqual(1, len(ledger.changes()))
        self.assertEqual(1, ledger.conflict_count)
        self.assertEqual("conflicting-payload-or-idempotency", ledger.conflicts()[0][4])

    def test_capability_manifest(self):
        got = CapabilityDescriptor("ledger", "1.2.0", frozenset({"replay", "revision"}))
        self.assertTrue(CompositionManifest({"ledger": got}, {"ledger": CapabilityDescriptor("ledger", "1.0.0", frozenset({"replay"}))}).validate())
        with self.assertRaises(ValueError): CompositionManifest({}, {"ledger": got}).validate()
