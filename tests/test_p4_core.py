import unittest
from datetime import datetime, timezone

from kb_pipeline.phase4_core import (
    BarrierState, EnvelopeOperation, IdentityCollision, IdentityRegistry,
    ProjectionBarrier, ReplayEnvelope, SemanticIdentity, resolve_legacy_identity,
)


class P4CoreTests(unittest.TestCase):
    def test_semantic_identity_is_stable_and_provenance_collision_fails_closed(self):
        identity = resolve_legacy_identity(tenant="t", object_id="42", connector="github",
                                           provider="p", source_instance="c1")
        self.assertEqual(("t", "github", "42"), identity.key)
        registry = IdentityRegistry()
        registry.register(identity, provider="p", connector="github", source_instance="c1")
        with self.assertRaises(IdentityCollision):
            registry.register(identity, provider="other", connector="github", source_instance="c1")

    def test_envelope_replay_is_deterministic(self):
        envelope = ReplayEnvelope("event", "idem", SemanticIdentity("t", "s", "id"), 1,
                                  EnvelopeOperation.UPSERT, {"text": "x"}, {"content_hash": "h"},
                                  {"provider": "p"}, {"readers": ["u"]}, "corr",
                                  datetime(2026, 1, 1, tzinfo=timezone.utc))
        self.assertEqual(envelope.serialize(), envelope.serialize())
        self.assertEqual(envelope, ReplayEnvelope.deserialize(envelope.serialize()))

    def test_barrier_never_reports_complete_before_minimum(self):
        barrier = ProjectionBarrier(accepted=8, applied=3)
        self.assertEqual(BarrierState.PENDING, barrier.observe(8).state)
        self.assertEqual(BarrierState.STALE, barrier.observe(2).state)
        barrier.blocked = True
        self.assertEqual(BarrierState.BLOCKED, barrier.observe(8).state)
        self.assertEqual(BarrierState.TIMEOUT, barrier.observe(8, timeout=True).state)


if __name__ == "__main__":
    unittest.main()
