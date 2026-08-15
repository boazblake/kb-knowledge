import unittest
from kb_pipeline.nango_adapter import (CapabilityStatus, FakeNangoTransport, NangoAdapter,
    NangoPoll, NangoRecord, NangoWebhook, RetryClass)
from kb_pipeline.protocol import IdentityNamespace, Operation
from kb_pipeline.security import Principal


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

    def test_approved_source_identity_is_namespace_complete(self):
        adapter = self.adapter()
        raw, change = adapter.webhook(NangoWebhook("identity", NangoRecord("object-7"))).envelopes[0]
        self.assertEqual(IdentityNamespace("github", "tenant-a", "conn-7", "nango", "conn-7"), change.source)
        self.assertEqual("nango://conn-7/object-7", raw.source.source_uri)
        self.assertEqual(("github", "tenant-a", "nango", "conn-7", "object-7"),
                         (change.source.provider, change.source.tenant, change.source.connector,
                          change.source.source_instance, change.object_id))

    def test_tenant_and_source_scope_are_fail_closed(self):
        principal = Principal("u", "tenant-a", frozenset({"reader"}), frozenset({"conn-7"}))
        self.assertTrue(principal.can_read("tenant-a", "conn-7"))
        self.assertFalse(principal.can_read("tenant-b", "conn-7"))
        self.assertFalse(principal.can_read("tenant-a", "other-connection"))

    def test_upsert_update_delete_and_permission_changes_preserve_order(self):
        adapter = self.adapter()
        records = (
            NangoRecord("x", {"text": "v1"}, revision=1),
            NangoRecord("x", {"text": "v2"}, revision=2),
            NangoRecord("x", operation=Operation.DELETE, revision=3),
            NangoRecord("x", permission_readers=frozenset({"reader"}), revision=4,
                        operation=Operation.PERMISSION),
        )
        changes = [adapter.webhook(NangoWebhook(f"e-{i}", record)).envelopes[0][1]
                   for i, record in enumerate(records)]
        self.assertEqual([Operation.UPSERT, Operation.UPSERT, Operation.DELETE, Operation.PERMISSION],
                         [change.operation for change in changes])
        self.assertEqual([1, 2, 3, 4], [change.revision for change in changes])
        self.assertEqual("e-0", changes[0].idempotency_key)
        self.assertEqual("e-3", changes[3].idempotency_key)

    def test_rate_limit_retry_classification_is_not_collapsed(self):
        retry = self.adapter((NangoPoll("rate-1", (), retry=RetryClass.RETRYABLE),)).poll()
        permanent = self.adapter((NangoPoll("blocked", (), retry=RetryClass.PERMANENT),)).poll()
        self.assertEqual(RetryClass.RETRYABLE, retry.retry)
        self.assertEqual(RetryClass.PERMANENT, permanent.retry)
        self.assertEqual(CapabilityStatus.DEGRADED, retry.capability_status)
        self.assertEqual(CapabilityStatus.DEGRADED, permanent.capability_status)

    def test_revision_ordering_requires_durable_cursor_ack(self):
        adapter = self.adapter((NangoPoll("10", (NangoRecord("x", revision=2),)),))
        batch = adapter.poll()
        self.assertEqual(2, batch.envelopes[0][1].revision)
        adapter.acknowledge(batch, ledger_accepted=False)
        self.assertIsNone(adapter.cursor)
        adapter.acknowledge(batch, ledger_accepted=True)
        self.assertEqual("10", adapter.cursor)

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

    def test_bearer_material_never_persisted(self):
        adapter = NangoAdapter("github", "conn", "tenant", oidc_token="secret")
        raw, change = adapter._envelope(NangoRecord("x", {"text": "ok", "oidc_token": "secret", "nested": {"bearer": "secret"}}), run_id="r")
        self.assertNotIn(b"secret", raw.payload)
        self.assertNotIn("oidc_token", raw.metadata)
        self.assertNotIn("bearer", str(getattr(change.value, "metadata", "")))


if __name__ == "__main__": unittest.main()
