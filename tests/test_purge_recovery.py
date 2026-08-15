import unittest
from datetime import datetime, timedelta, timezone

from kb_pipeline.purge import (PurgeCoordinator, PurgeStatus, ReceiptStatus,
                               RetentionDecision, StoreReceipt, PurgeIntent)
from kb_pipeline.domain import ACL, CanonicalDocument, SourceVersion
from kb_pipeline.storage import SQLiteStore
from tempfile import TemporaryDirectory
from pathlib import Path


class Repo:
    def __init__(self): self.intents = {}; self.receipts = {}; self.events = []; self.order = []
    def create_purge_intent(self, intent):
        if intent.idempotency_key in self.intents: return self.intents[intent.idempotency_key]
        self.intents[intent.idempotency_key] = intent; return intent
    def tombstone_for_purge(self, purge_id, target, actor, correlation_id):
        self.order.append("tombstone"); return (target,)
    def save_purge_receipt(self, receipt): self.receipts[(receipt.purge_id, receipt.store)] = receipt
    def purge_receipts(self, purge_id): return tuple(r for (pid, _), r in self.receipts.items() if pid == purge_id)
    def audit_purge(self, intent, action): self.events.append((action, intent.correlation_id))


class Hook:
    def __init__(self, name, failures=0, missing=False, repo=None): self.name=name; self.failures=failures; self.missing=missing; self.calls=0; self.repo=repo
    def delete(self, intent: PurgeIntent, object_ids: tuple[str, ...]):
        self.calls += 1
        if self.repo: self.repo.order.append(self.name)
        if self.failures and self.calls <= self.failures: raise TimeoutError("provider")
        if self.missing: return None
        return StoreReceipt(intent.purge_id, self.name, ReceiptStatus.COMPLETE, correlation_id=intent.correlation_id)


class PurgeRecoveryTests(unittest.TestCase):
    def decision(self, **kwargs): return RetentionDecision("customer", **kwargs)
    def test_duplicate_intent_is_idempotent(self):
        repo = Repo(); coordinator = PurgeCoordinator(repo, ())
        first = coordinator.request(idempotency_key="k", target="doc", actor="ops", approved_by="reviewer", decision=self.decision())
        second = coordinator.request(idempotency_key="k", target="doc", actor="ops", approved_by="reviewer", decision=self.decision())
        self.assertEqual(first, second)
        self.assertEqual(1, len(repo.intents))
    def test_tombstone_precedes_deletion_and_partial_failure_fails_closed(self):
        repo = Repo(); hooks = tuple([Hook("authority", repo=repo), Hook("raw_object", failures=1, repo=repo), Hook("projection", repo=repo), Hook("cache", repo=repo), Hook("workflow_state", repo=repo), Hook("backup_replica", repo=repo)])
        c = PurgeCoordinator(repo, hooks); intent = c.request(idempotency_key="p", target="d", actor="ops", approved_by="reviewer", decision=self.decision())
        self.assertEqual(PurgeStatus.INCOMPLETE, c.execute(intent)); self.assertEqual("tombstone", repo.order[0]); self.assertEqual(ReceiptStatus.FAILED, repo.receipts[(intent.purge_id, "raw_object")].status)
        self.assertEqual(PurgeStatus.COMPLETE, c.retry(intent)); self.assertEqual(2, hooks[1].calls)
    def test_missing_receipt_is_unknown(self):
        repo = Repo(); c = PurgeCoordinator(repo, (Hook("raw_object", missing=True),), required_stores=("raw_object",))
        intent = c.request(idempotency_key="m", target="d", actor="ops", approved_by="reviewer", decision=self.decision())
        self.assertEqual(PurgeStatus.INCOMPLETE, c.execute(intent)); self.assertEqual(ReceiptStatus.UNKNOWN, repo.purge_receipts(intent.purge_id)[0].status)
    def test_retention_and_legal_hold_block(self):
        now = datetime.now(timezone.utc); repo = Repo(); c = PurgeCoordinator(repo, ())
        for decision in (self.decision(retain_until=now + timedelta(days=1)), self.decision(legal_hold=True)):
            with self.assertRaises(PermissionError): c.request(idempotency_key="hold", target="d", actor="ops", approved_by="reviewer", decision=decision)
    def test_role_approval_boundary(self):
        with self.assertRaises(PermissionError): PurgeCoordinator(Repo(), ()).request(idempotency_key="x", target="d", actor="ops", approved_by="ops", decision=self.decision())
    def test_restore_replay_cannot_resurrect_tombstone_or_retrieve_purged_object(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "state.sqlite"
            observed = datetime.now(timezone.utc)
            doc = CanonicalDocument("doc", SourceVersion("source", "1", "file:doc", observed, "hash"), "title", "secret", ACL(frozenset({"reader"})))
            store = SQLiteStore(path); self.assertTrue(store.put(doc)); store.tombstone("doc"); store.db.close()
            restored = SQLiteStore(path)
            self.assertFalse(restored.put(doc))  # replay/restore UPSERT is fenced by durable tombstone
            self.assertEqual([], restored.search("secret"))  # negative retrieval after purge/tombstone


if __name__ == "__main__": unittest.main()
