import unittest
from kb_pipeline.nango_adapter import (CapabilityStatus, FakeNangoTransport, NangoAdapter,
    NangoPoll, NangoRecord, NangoWebhook, RetryClass)
from kb_pipeline.protocol import Operation


class NangoAdapterTests(unittest.TestCase):
    def adapter(self, pages=()):
        return NangoAdapter("github", "conn-7", "tenant-a", FakeNangoTransport(pages))

    def test_poll_cursor_requires_durable_ack_and_retries(self):
        page = NangoPoll("c1", (NangoRecord("x", {"text": "hi"}),), run_id="run-1", retry=RetryClass.RETRYABLE)
        adapter = self.adapter((page,))
        batch = adapter.poll(); self.assertIsNone(adapter.cursor)
        self.assertEqual(RetryClass.RETRYABLE, batch.retry)
        self.assertEqual("degraded", batch.capability_status.value)
        adapter.acknowledge(batch, ledger_accepted=False); self.assertIsNone(adapter.cursor)
        self.assertEqual("c1", adapter.poll().cursor)
        adapter.acknowledge(batch, ledger_accepted=True); self.assertEqual("c1", adapter.cursor)

    def test_duplicate_webhook_is_idempotent(self):
        adapter = self.adapter()
        event = NangoWebhook("evt-1", NangoRecord("x", {"text": "hi"}), run_id="run")
        self.assertEqual(1, len(adapter.webhook(event).envelopes))
        self.assertEqual(0, len(adapter.webhook(event).envelopes))

    def test_delete_and_full_identity_provenance(self):
        adapter = self.adapter()
        batch = adapter.webhook(NangoWebhook("delete-1", NangoRecord("x", operation=Operation.DELETE), run_id="r"))
        raw, change = batch.envelopes[0]
        self.assertEqual(Operation.DELETE, change.operation); self.assertEqual("conn-7", change.source.source_instance)
        self.assertEqual("r", change.provenance.identifier); self.assertIn("source_hash", raw.metadata)

    def test_incomplete_reconciliation_cannot_delete(self):
        adapter = self.adapter(); adapter._known_objects.add("gone")
        batch = adapter.reconcile_snapshot((), complete=False, run_id="partial")
        self.assertEqual(0, len(batch.envelopes))
        batch = adapter.reconcile_snapshot((), complete=True, run_id="full")
        self.assertEqual(Operation.DELETE, batch.envelopes[0][1].operation)

    def test_unknown_permission_denies(self):
        _, change = self.adapter().webhook(NangoWebhook("e", NangoRecord("x", permission_readers=None, permission_resolved=False))).envelopes[0]
        self.assertFalse(change.permissions.resolved); self.assertFalse(change.permissions.permits("anyone"))

    def test_capability_and_retention_limitations_are_explicit(self):
        adapter = self.adapter(); self.assertIn("poll", adapter.capability.features)
        self.assertNotIn("archive", adapter.capability.features)
        self.assertEqual("partial", CapabilityStatus.PARTIAL.value)


if __name__ == "__main__": unittest.main()
