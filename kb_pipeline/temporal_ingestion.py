"""Temporal durable ingestion lane.

Temporal remains orchestration authority. PostgreSQL outbox remains acceptance
authority; claiming an outbox row and marking it applied are separate durable
steps, so accepted-but-not-started work is reconciled safely.
"""
from __future__ import annotations

import asyncio
import hashlib
import random
import re
from dataclasses import dataclass
from datetime import timedelta
from typing import Any, Awaitable, Callable, Mapping
from .telemetry import span as telemetry_span

try:
    from temporalio import activity, workflow
    from temporalio.common import RetryPolicy, WorkflowIDReusePolicy
    from temporalio.client import Client
    from temporalio.worker import Worker
    TEMPORAL_AVAILABLE = True
except ImportError:  # local contract tests may run without optional production deps
    TEMPORAL_AVAILABLE = False
    activity = workflow = None
    RetryPolicy = WorkflowIDReusePolicy = Client = Worker = None


class TemporalUnavailable(RuntimeError):
    pass


@dataclass(frozen=True)
class IngestionEvent:
    idempotency_key: str
    tenant: str
    workload: str
    payload: Mapping[str, Any]


@dataclass(frozen=True)
class TemporalSettings:
    task_queue: str = "kb-ingestion"
    start_to_close_seconds: int = 300
    heartbeat_seconds: int = 30
    workflow_timeout_seconds: int = 1800
    max_attempts: int = 5
    initial_backoff_seconds: int = 2
    max_backoff_seconds: int = 60
    jitter_ratio: float = 0.2

    def validate(self) -> None:
        if min(self.start_to_close_seconds, self.heartbeat_seconds, self.workflow_timeout_seconds,
               self.max_attempts, self.initial_backoff_seconds, self.max_backoff_seconds) <= 0:
            raise ValueError("Temporal timeouts and retry bounds must be positive")
        if not 0 <= self.jitter_ratio <= 1:
            raise ValueError("jitter_ratio must be between zero and one")


def workflow_id(event: IngestionEvent) -> str:
    digest = hashlib.sha256(event.idempotency_key.encode()).hexdigest()[:24]
    tenant = re.sub(r"[^a-zA-Z0-9_-]", "_", event.tenant)[:40]
    workload = re.sub(r"[^a-zA-Z0-9_-]", "_", event.workload)[:40]
    return f"ingest-{tenant}-{workload}-{digest}"


def bounded_jitter(event_key: str, attempt: int, base_seconds: float, ratio: float = .2) -> float:
    """Deterministic jitter: replay-safe and bounded, unlike global random state."""
    seed = int(hashlib.sha256(f"{event_key}:{attempt}".encode()).hexdigest()[:16], 16)
    return base_seconds * (1 + random.Random(seed).uniform(-ratio, ratio))


def require_temporal(endpoint: str, namespace: str) -> None:
    if not TEMPORAL_AVAILABLE:
        raise TemporalUnavailable("temporalio SDK required")
    if not endpoint or not namespace:
        raise ValueError("Temporal endpoint and namespace required")


async def connect_temporal(endpoint: str, namespace: str):
    """Connect to real Temporal; never creates an in-process substitute."""
    require_temporal(endpoint, namespace)
    return await Client.connect(endpoint, namespace=namespace)


class TemporalWorkflowBoundary:
    test_only = False

    def __init__(self, client: Any, settings: TemporalSettings | None = None):
        if client is None:
            raise ValueError("Temporal client required")
        self.client = client
        self.settings = settings or TemporalSettings()
        self.settings.validate()

    async def start_ingestion_async(self, event: IngestionEvent):
        if not TEMPORAL_AVAILABLE:
            raise TemporalUnavailable("temporalio SDK required")
        return await self.client.start_workflow(
            ingestion_workflow, event, id=workflow_id(event), task_queue=self.settings.task_queue,
            execution_timeout=timedelta(seconds=self.settings.workflow_timeout_seconds),
            id_reuse_policy=WorkflowIDReusePolicy.REJECT_DUPLICATE,
        )

    def start_ingestion(self, workflow_id_value: str, payload: Mapping[str, Any]):
        """Compatibility port; caller supplies already-derived durable ID."""
        event = IngestionEvent(str(payload.get("idempotency_key", workflow_id_value)),
                               str(payload["tenant"]), str(payload["workload"]), payload)
        return _run_sync(self.start_ingestion_async(event))


def _run_sync(awaitable: Awaitable[Any]):
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(awaitable)
    raise RuntimeError("use start_ingestion_async inside running event loop")


async def reconcile_outbox(repository: Any, boundary: Any, *, worker: str,
                           tenant: str, workload: str, limit: int = 100, telemetry: Any = None) -> int:
    """Start every claimed accepted event, marking applied only after Temporal accepts it."""
    with telemetry_span(telemetry, "outbox.claim", component="outbox", tenant=tenant, workload=workload):
        rows = repository.claim_outbox(worker, tenant=tenant, workload=workload, limit=limit)
    started = 0
    for row in rows:
        event = IngestionEvent(str(row["idempotency_key"]), tenant, workload, row["payload"])
        try:
            with telemetry_span(telemetry, "workflow.start", component="workflow", tenant=tenant, workload=workload):
                await boundary.start_ingestion_async(event)
            if "lease_token" in row:
                repository.mark_outbox_applied(row["sequence"], worker, tenant=tenant, workload=workload,
                                               lease_token=row["lease_token"])
            else:
                repository.mark_outbox_applied(row["sequence"], worker)
            if telemetry: telemetry.counter("outbox.applied", tenant=tenant, workload=workload)
            started += 1
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            failure = f"Temporal start failed: {type(exc).__name__}"
            if "lease_token" in row:
                repository.mark_outbox_failed(row["sequence"], failure, row["worker"], tenant=tenant,
                                              workload=workload, lease_token=row["lease_token"])
            else:
                # Compatibility with test/dummy repositories; PostgreSQL claims always include token.
                repository.mark_outbox_failed(row["sequence"], failure)
            if telemetry: telemetry.counter("workflow.retry", tenant=tenant, workload=workload, retryable=True)
    return started


def manual_retry_dead_letter(repository: Any, sequence: int, *, operator: Any, telemetry: Any = None) -> None:
    """Explicit operator boundary. No automatic DLQ replay."""
    subject = getattr(operator, "subject", operator if isinstance(operator, str) else "")
    if not isinstance(subject, str) or not subject.strip():
        raise ValueError("operator identity required")
    retry = getattr(repository, "retry_dead_letter", None)
    if retry is None:
        raise RuntimeError("repository does not expose manual DLQ retry")
    retry(sequence, operator=operator)
    if telemetry: telemetry.counter("dlq.manual_retry", outcome="accepted")


if TEMPORAL_AVAILABLE:
    _activity_handler: Callable | None = None

    def configure_activity_handler(handler: Callable) -> None:
        """Bind application activity handler before constructing Worker."""
        global _activity_handler
        _activity_handler = handler

    @activity.defn
    async def ingest_event_activity(event: IngestionEvent) -> str:
        activity.heartbeat({"tenant": event.tenant, "workload": event.workload})
        if activity.is_cancelled():
            raise asyncio.CancelledError()
        if _activity_handler is None:
            raise RuntimeError("ingestion activity handler not configured")
        result = _activity_handler(event)
        if asyncio.iscoroutine(result):
            result = await result
        activity.heartbeat({"status": "accepted"})
        return str(result)

    @workflow.defn
    class IngestionWorkflow:
        @workflow.run
        async def run(self, event: IngestionEvent) -> str:
            settings = TemporalSettings()
            policy = RetryPolicy(initial_interval=timedelta(seconds=settings.initial_backoff_seconds),
                                 backoff_coefficient=2.0,
                                 maximum_interval=timedelta(seconds=settings.max_backoff_seconds),
                                 maximum_attempts=settings.max_attempts)
            return await workflow.execute_activity(
                ingest_event_activity, event, start_to_close_timeout=timedelta(seconds=settings.start_to_close_seconds),
                heartbeat_timeout=timedelta(seconds=settings.heartbeat_seconds), retry_policy=policy)

    ingestion_workflow = IngestionWorkflow.run

    def create_worker(client: Any, activities: list[Callable], settings: TemporalSettings | None = None):
        selected = settings or TemporalSettings()
        selected.validate()
        return Worker(client, task_queue=selected.task_queue,
                      workflows=[IngestionWorkflow], activities=activities)
else:
    async def ingestion_workflow(event: IngestionEvent):
        raise TemporalUnavailable("temporalio SDK required")

    def create_worker(client: Any, activities: list[Callable], settings: TemporalSettings | None = None):
        raise TemporalUnavailable("temporalio SDK required")
