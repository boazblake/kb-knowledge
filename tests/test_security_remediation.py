import sqlite3
import unittest
from datetime import datetime, timedelta, timezone

from kb_pipeline.domain import ACL, CanonicalDocument, SourceVersion
from kb_pipeline.ingestion_slice import IngestionSlice
from kb_pipeline.protocol import (CanonicalChange, IdentityNamespace, Operation,
                                  PermissionState, ProvenanceLink, RelationalReferenceLedger,
                                  RevisionOutcome)


def make_change(tenant="tenant-a", revision=1, operation=Operation.UPSERT,
                text="secret", key=None):
    source = IdentityNamespace("provider", tenant, connector="workload-a", source_instance="source")
    now = datetime.now(timezone.utc)
    doc = CanonicalDocument("object", SourceVersion("object", str(revision), "s://object", now, f"hash-{revision}"),
                            "object", text, ACL(frozenset({"reader"})))
    return CanonicalChange("object", source, revision, operation,
                           None if operation == Operation.DELETE else doc,
                           key or f"{tenant}:{revision}:{operation.value}",
                           ProvenanceLink("connector", "event"), PermissionState(doc.acl), occurred_at=now)


class SecurityRemediationTests(unittest.TestCase):
    def test_outbox_claim_is_tenant_and_workload_scoped(self):
        ledger = RelationalReferenceLedger(sqlite3.connect(":memory:"))
        ledger.append(make_change("tenant-a"))
        ledger.append(make_change("tenant-b"))
        self.assertEqual((), ledger.claim_outbox("worker", tenant="tenant-a", workload="other"))
        self.assertEqual((1,), ledger.claim_outbox("worker", tenant="tenant-a", workload="workload-a"))
        self.assertEqual((2,), ledger.claim_outbox("worker-2", tenant="tenant-b", workload="workload-a"))

    def test_expired_claim_is_reclaimed_after_worker_crash(self):
        ledger = RelationalReferenceLedger(sqlite3.connect(":memory:"))
        ledger.append(make_change())
        now = datetime.now(timezone.utc)
        self.assertEqual((1,), ledger.claim_outbox("crashed", now=now, lease_seconds=1, tenant="tenant-a", workload="workload-a"))
        self.assertEqual((1,), ledger.claim_outbox("recovery", now=now + timedelta(seconds=2), tenant="tenant-a", workload="workload-a"))

    def test_checkpoint_is_monotonic_and_idempotent(self):
        ledger = RelationalReferenceLedger(sqlite3.connect(":memory:"))
        ledger.append(make_change())
        ledger.save_checkpoint("stream", 1)
        ledger.save_checkpoint("stream", 1)
        with self.assertRaises(ValueError):
            ledger.save_checkpoint("stream", 0)

    def test_idempotency_key_conflict_is_not_duplicate(self):
        ledger = RelationalReferenceLedger(sqlite3.connect(":memory:"))
        first = make_change(key="same-key")
        conflict = make_change(text="tampered", key="same-key")
        self.assertEqual(RevisionOutcome.ACCEPTED, ledger.append_outcome(first))
        self.assertEqual(RevisionOutcome.CONFLICT, ledger.append_outcome(conflict))

    def test_revision_delete_and_permission_operations_are_preserved(self):
        ledger = RelationalReferenceLedger(sqlite3.connect(":memory:"))
        self.assertEqual(RevisionOutcome.ACCEPTED, ledger.append_outcome(make_change(revision=1)))
        self.assertEqual(RevisionOutcome.ACCEPTED, ledger.append_outcome(make_change(revision=2, operation=Operation.PERMISSION)))
        self.assertEqual(RevisionOutcome.ACCEPTED, ledger.append_outcome(make_change(revision=3, operation=Operation.DELETE)))
        changes = ledger.changes()
        self.assertEqual((1, 2, 3), tuple(change.revision for change in changes))
        self.assertEqual((Operation.UPSERT, Operation.PERMISSION, Operation.DELETE), tuple(change.operation for change in changes))

    def test_connector_failure_does_not_ack_or_start_workflow(self):
        class BrokenConnector:
            connector = "broken"
            provider_config = "provider"
            tenant = "tenant-a"
            connection = "source"
            def poll(self): raise RuntimeError("connector unavailable")
        class Service:
            def ingest(self, item, job): return True
        class Workflow:
            def start_ingestion(self, *args): raise AssertionError("must not start")
        with self.assertRaises(RuntimeError):
            IngestionSlice(BrokenConnector(), Service(), Workflow()).poll_once("job")


if __name__ == "__main__":
    unittest.main()
