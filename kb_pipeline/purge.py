"""Purge intent, tombstone, receipt, and recovery semantics.

This module is orchestration glue around existing authority, storage, projection,
cache, workflow, and backup adapters. It owns no storage or workflow engine.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Protocol


class PurgeStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETE = "complete"
    INCOMPLETE = "incomplete"
    UNKNOWN = "unknown"
    BLOCKED = "blocked"


class ReceiptStatus(str, Enum):
    COMPLETE = "complete"
    FAILED = "failed"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class RetentionDecision:
    data_class: str
    retain_until: datetime | None = None
    legal_hold: bool = False
    reason: str = ""

    def allowed(self, now: datetime) -> bool:
        return not self.legal_hold and (self.retain_until is None or now >= self.retain_until)


@dataclass(frozen=True)
class PurgeIntent:
    purge_id: str
    idempotency_key: str
    target: str
    actor: str
    correlation_id: str
    decision: RetentionDecision


@dataclass(frozen=True)
class StoreReceipt:
    purge_id: str
    store: str
    status: ReceiptStatus
    detail: str = ""
    correlation_id: str = ""


class PurgeRepository(Protocol):
    def create_purge_intent(self, intent: PurgeIntent) -> PurgeIntent: ...
    def tombstone_for_purge(self, purge_id: str, target: str, actor: str, correlation_id: str) -> tuple[str, ...]: ...
    def save_purge_receipt(self, receipt: StoreReceipt) -> None: ...
    def purge_receipts(self, purge_id: str) -> tuple[StoreReceipt, ...]: ...
    def audit_purge(self, intent: PurgeIntent, action: str) -> None: ...


class DeletionHook(Protocol):
    name: str
    def delete(self, intent: PurgeIntent, object_ids: tuple[str, ...]) -> StoreReceipt | None: ...


class PurgeAuthorization:
    """Approval boundary. Caller must provide privileged actor and explicit approval."""
    @staticmethod
    def require(actor: str, approved_by: str | None) -> None:
        if not actor.strip() or not approved_by or not approved_by.strip():
            raise PermissionError("purge requires actor and independent approval")
        if actor == approved_by:
            raise PermissionError("purge approval must be independent")


class PurgeCoordinator:
    STORES = ("authority", "raw_object", "projection", "cache", "workflow_state", "backup_replica")

    def __init__(self, repository: PurgeRepository, hooks: tuple[DeletionHook, ...], *, required_stores=None, clock=None):
        names = tuple(h.name for h in hooks)
        if len(names) != len(set(names)) or any(name not in self.STORES for name in names):
            raise ValueError("hooks must name supported stores uniquely")
        self.repository, self.hooks, self.clock = repository, hooks, clock or (lambda: datetime.now(timezone.utc))
        self.required_stores = tuple(required_stores or self.STORES)
        if any(name not in self.STORES for name in self.required_stores): raise ValueError("unsupported required store")

    def request(self, *, idempotency_key: str, target: str, actor: str,
                approved_by: str | None, decision: RetentionDecision,
                correlation_id: str | None = None) -> PurgeIntent:
        PurgeAuthorization.require(actor, approved_by)
        if not idempotency_key.strip() or not target.strip(): raise ValueError("idempotency key and target required")
        if not decision.allowed(self.clock()): raise PermissionError("retention or legal hold blocks purge")
        correlation_id = correlation_id or hashlib.sha256(idempotency_key.encode()).hexdigest()[:24]
        intent = PurgeIntent(hashlib.sha256((idempotency_key + target).encode()).hexdigest(), idempotency_key,
                             target, actor, correlation_id, decision)
        stored = self.repository.create_purge_intent(intent)
        self.repository.audit_purge(stored, "purge_intent")
        return stored

    def execute(self, intent: PurgeIntent) -> PurgeStatus:
        # Durable authority transaction must commit tombstones before any hook runs.
        object_ids = self.repository.tombstone_for_purge(intent.purge_id, intent.target, intent.actor, intent.correlation_id)
        self.repository.audit_purge(intent, "tombstone_committed")
        for hook in self.hooks:
            existing = {r.store: r for r in self.repository.purge_receipts(intent.purge_id)}
            if existing.get(hook.name, StoreReceipt(intent.purge_id, hook.name, ReceiptStatus.UNKNOWN)).status == ReceiptStatus.COMPLETE:
                continue
            try:
                receipt = hook.delete(intent, object_ids)
                receipt = receipt or StoreReceipt(intent.purge_id, hook.name, ReceiptStatus.UNKNOWN, "missing receipt", intent.correlation_id)
            except Exception as exc:
                receipt = StoreReceipt(intent.purge_id, hook.name, ReceiptStatus.FAILED, type(exc).__name__, intent.correlation_id)
            self.repository.save_purge_receipt(receipt)
        for store in self.required_stores:
            if store not in {r.store for r in self.repository.purge_receipts(intent.purge_id)}:
                self.repository.save_purge_receipt(StoreReceipt(intent.purge_id, store, ReceiptStatus.UNKNOWN, "deletion hook unavailable", intent.correlation_id))
        receipts = self.repository.purge_receipts(intent.purge_id)
        status = (PurgeStatus.INCOMPLETE if any(r.status in (ReceiptStatus.FAILED, ReceiptStatus.UNKNOWN) for r in receipts)
                  or any(store not in {r.store for r in receipts} for store in self.required_stores)
                  else PurgeStatus.COMPLETE)
        setter = getattr(self.repository, "set_purge_status", None)
        if setter: setter(intent.purge_id, status)
        return status

    def retry(self, intent: PurgeIntent) -> PurgeStatus:
        return self.execute(intent)  # tombstone and complete receipts are idempotent


def replay_preserving_tombstones(ledger, target) -> None:
    """Replay hook: DELETE events remain authoritative; UPSERT cannot resurrect them."""
    for change in ledger.changes():
        target.apply(change)


# Temporal durable boundary. SDK unavailable means production workflow cannot start.
try:
    from temporalio import activity, workflow
    from temporalio.common import RetryPolicy
    TEMPORAL_AVAILABLE = True
except ImportError:
    TEMPORAL_AVAILABLE = False

if TEMPORAL_AVAILABLE:
    _runner: PurgeCoordinator | None = None

    def configure_purge_runner(runner: PurgeCoordinator) -> None:
        global _runner
        _runner = runner

    @activity.defn
    async def purge_activity(intent: PurgeIntent) -> str:
        if _runner is None: raise RuntimeError("purge runner not configured")
        return _runner.execute(intent).value

    @workflow.defn
    class PurgeWorkflow:
        @workflow.run
        async def run(self, intent: PurgeIntent) -> str:
            return await workflow.execute_activity(purge_activity, intent, start_to_close_timeout=__import__("datetime").timedelta(minutes=5),
                                                   retry_policy=RetryPolicy(maximum_attempts=5))
else:
    async def purge_activity(intent): raise RuntimeError("temporalio SDK required")
