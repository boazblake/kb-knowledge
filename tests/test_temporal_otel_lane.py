import asyncio
import unittest

from kb_pipeline.telemetry import safe_attributes
from kb_pipeline.temporal_ingestion import (
    IngestionEvent,
    TemporalSettings,
    TemporalUnavailable,
    bounded_jitter,
    manual_retry_dead_letter,
    reconcile_outbox,
    require_temporal,
    workflow_id,
)


class TemporalOtelLaneTests(unittest.TestCase):
    def test_workflow_id_is_idempotent_and_scoped(self):
        event = IngestionEvent("same-event", "tenant/one", "github", {})
        self.assertEqual(workflow_id(event), workflow_id(event))
        self.assertIn("tenant_one", workflow_id(event))
        self.assertNotEqual(workflow_id(event), workflow_id(IngestionEvent("other", "tenant/one", "github", {})))

    def test_retry_jitter_is_deterministic_and_bounded(self):
        value = bounded_jitter("event", 2, 10, .2)
        self.assertEqual(value, bounded_jitter("event", 2, 10, .2))
        self.assertGreaterEqual(value, 8)
        self.assertLessEqual(value, 12)

    def test_safe_attributes_drop_payload_and_credentials(self):
        attrs = safe_attributes({"tenant": "t", "payload": "secret body", "authorization": "bearer", "attempt": 2})
        self.assertEqual({"tenant": "t", "attempt": 2}, attrs)

    def test_reconcile_marks_applied_only_after_start(self):
        class Repo:
            def __init__(self): self.applied = []; self.failed = []
            def claim_outbox(self, worker, **kwargs):
                return ({"sequence": 4, "idempotency_key": "e", "payload": {}},)
            def mark_outbox_applied(self, sequence, worker): self.applied.append((sequence, worker))
            def mark_outbox_failed(self, sequence, reason): self.failed.append((sequence, reason))

        class Boundary:
            async def start_ingestion_async(self, event): return object()

        repo = Repo()
        count = asyncio.run(reconcile_outbox(repo, Boundary(), worker="w", tenant="t", workload="c"))
        self.assertEqual(1, count)
        self.assertEqual([(4, "w")], repo.applied)
        self.assertFalse(repo.failed)

    def test_failed_start_stays_retryable_or_reaches_dlq_boundary(self):
        class Repo:
            def claim_outbox(self, worker, **kwargs):
                return ({"sequence": 4, "idempotency_key": "e", "payload": {}},)
            def mark_outbox_failed(self, sequence, reason): self.reason = reason

        class Boundary:
            async def start_ingestion_async(self, event): raise ConnectionError("down")

        repo = Repo()
        self.assertEqual(0, asyncio.run(reconcile_outbox(repo, Boundary(), worker="w", tenant="t", workload="c")))
        self.assertIn("ConnectionError", repo.reason)

    def test_manual_retry_requires_operator_and_repository_boundary(self):
        class Repo:
            def retry_dead_letter(self, sequence, *, operator): self.called = (sequence, operator)
        repo = Repo()
        with self.assertRaises(ValueError): manual_retry_dead_letter(repo, 1, operator=" ")
        manual_retry_dead_letter(repo, 1, operator="oncall")
        self.assertEqual((1, "oncall"), repo.called)

    def test_production_temporal_fails_closed_when_sdk_missing(self):
        with self.assertRaises(TemporalUnavailable): require_temporal("localhost:7233", "default")


if __name__ == "__main__":
    unittest.main()
