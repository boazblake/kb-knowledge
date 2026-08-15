"""Narrow, synthetic Nango-shaped adapter experiment.

This module deliberately contains no Nango SDK or network code.  It converts a
small provider-like transport contract into protocol envelopes; caller owns
ledger append/acknowledgement and projections remain outside this boundary.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Iterable, Mapping, Protocol

from .domain import ACL, CanonicalDocument, RawRecord, SourceVersion
from .protocol import (CanonicalChange, CapabilityDescriptor, IdentityNamespace,
                       Operation, PermissionState, ProvenanceLink)


class RetryClass(str, Enum):
    NONE = "none"
    RETRYABLE = "retryable"
    PERMANENT = "permanent"


class CapabilityStatus(str, Enum):
    COMPLETE = "complete"
    PARTIAL = "partial"
    DEGRADED = "degraded"


@dataclass(frozen=True)
class NangoRecord:
    object_id: str
    payload: Mapping[str, object] = field(default_factory=dict)
    revision: int = 1
    operation: Operation = Operation.UPSERT
    source_hash: str | None = None
    occurred_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    permission_readers: frozenset[str] | None = None
    permission_resolved: bool = True
    data_class: str = "default"


@dataclass(frozen=True)
class NangoWebhook:
    event_id: str
    record: NangoRecord
    cursor: str | None = None
    run_id: str = ""
    retry: RetryClass = RetryClass.NONE


@dataclass(frozen=True)
class NangoPoll:
    cursor: str
    records: tuple[NangoRecord, ...]
    complete: bool = True
    run_id: str = ""
    retry: RetryClass = RetryClass.NONE


@dataclass(frozen=True)
class AdapterBatch:
    cursor: str | None
    envelopes: tuple[tuple[RawRecord, CanonicalChange], ...]
    complete: bool
    run_id: str
    retry: RetryClass = RetryClass.NONE
    capability: CapabilityDescriptor = field(default_factory=lambda: CapabilityDescriptor("nango-adapter", "0.1.0"))
    capability_status: CapabilityStatus = CapabilityStatus.COMPLETE


class NangoTransport(Protocol):
    def poll(self, cursor: str | None) -> NangoPoll: ...


class FakeNangoTransport:
    """Deterministic fixture transport; never touches credentials or network."""
    test_only = True
    def __init__(self, pages: Iterable[NangoPoll]):
        self.pages = list(pages)
        self.calls: list[str | None] = []

    def poll(self, cursor: str | None) -> NangoPoll:
        self.calls.append(cursor)
        for page in self.pages:
            if page.cursor != cursor:
                return page
        return NangoPoll(cursor or "0", (), True, "fixture-empty")


class NangoAdapter:
    """Translate synthetic poll/webhook input into full provider-neutral envelopes."""
    capability = CapabilityDescriptor(
        "nango-adapter", "0.1.0",
        frozenset({"poll", "webhook", "object-key", "provenance", "deletes", "permission-state"}),
    )

    def __init__(self, provider_config: str, connection: str, tenant: str,
                 transport: NangoTransport | None = None, *, connector: str = "nango", cursor_store=None,
                 oidc_token: str | None = None):
        self.provider_config, self.connection, self.tenant = provider_config, connection, tenant
        self.connector, self.transport, self.oidc_token = connector, transport, oidc_token
        self.cursor_store = cursor_store
        self.cursor: str | None = self._load_cursor()
        self._acknowledged: set[str] = set()
        self._seen: set[str] = set()
        self._known_objects: set[str] = set()

    def _load_cursor(self):
        if self.cursor_store is None:
            return None
        checkpoint = self.cursor_store.get_checkpoint(self.source)
        return checkpoint[0] if checkpoint else None

    @property
    def source(self) -> IdentityNamespace:
        return IdentityNamespace(self.provider_config, self.tenant, self.connection,
                                 self.connector, self.connection)

    def _envelope(self, record: NangoRecord, *, run_id: str, event_id: str | None = None):
        payload = json.dumps(dict(record.payload), sort_keys=True, separators=(",", ":")).encode()
        digest = record.source_hash or hashlib.sha256(payload).hexdigest()
        source_id = record.object_id
        version = str(record.revision)
        source_version = SourceVersion(source_id, version, f"nango://{self.connection}/{source_id}",
                                       record.occurred_at, digest)
        raw_id = event_id or f"{self.source.key}:{source_id}:{version}:{digest}"
        raw = RawRecord(source_version, payload,
                        {"provider_config": self.provider_config, "connection": self.connection,
                         "tenant": self.tenant, "run_id": run_id, "source_revision": version,
                         "source_hash": digest}, envelope_id=raw_id)
        if self.oidc_token is not None:
            raw = RawRecord(source_version, payload,
                            {**raw.metadata, "oidc_token": self.oidc_token}, envelope_id=raw_id)
        permissions = PermissionState(ACL(record.permission_readers), record.permission_resolved,
                                      record.occurred_at)
        value = None
        if record.operation != Operation.DELETE:
            value = CanonicalDocument(source_id, source_version, str(record.payload.get("title", source_id)),
                                       str(record.payload.get("text", "")), permissions.acl,
                                       {"provider_config": self.provider_config, "connection": self.connection})
        change = CanonicalChange(source_id, self.source, record.revision, record.operation, value,
                                 raw_id, ProvenanceLink("nango-run", run_id,
                                 ProvenanceLink("nango-event", event_id or raw_id)), permissions,
                                 record.data_class, record.occurred_at)
        return raw, change

    def poll(self) -> AdapterBatch:
        if self.transport is None:
            raise RuntimeError("transport required for poll")
        page = self.transport.poll(self.cursor)
        pairs = tuple(self._envelope(r, run_id=page.run_id) for r in page.records)
        status = CapabilityStatus.COMPLETE if page.complete else CapabilityStatus.PARTIAL
        if page.retry != RetryClass.NONE:
            status = CapabilityStatus.DEGRADED
        return AdapterBatch(page.cursor, pairs, page.complete, page.run_id, page.retry, self.capability, status)

    def acknowledge(self, batch: AdapterBatch, *, ledger_accepted: bool) -> None:
        """Advance cursor only after durable ledger acceptance."""
        if ledger_accepted and batch.complete and batch.cursor is not None:
            self.cursor = batch.cursor
            self._acknowledged.add(batch.cursor)
            self._known_objects.update(change.object_id for _, change in batch.envelopes)
            if self.cursor_store is not None:
                self.cursor_store.checkpoint(self.connector, batch.cursor, True, source=self.source)

    def webhook(self, event: NangoWebhook) -> AdapterBatch:
        key = event.event_id
        if key in self._seen:
            return AdapterBatch(event.cursor, (), True, event.run_id, event.retry, self.capability,
                                CapabilityStatus.DEGRADED if event.retry != RetryClass.NONE else CapabilityStatus.COMPLETE)
        self._seen.add(key)
        return AdapterBatch(event.cursor, (self._envelope(event.record, run_id=event.run_id, event_id=key),),
                            True, event.run_id, event.retry, self.capability,
                            CapabilityStatus.DEGRADED if event.retry != RetryClass.NONE else CapabilityStatus.COMPLETE)

    def reconcile_snapshot(self, records: Iterable[NangoRecord], *, complete: bool,
                           run_id: str) -> AdapterBatch:
        current = tuple(records)
        pairs = [self._envelope(r, run_id=run_id) for r in current]
        current_ids = {r.object_id for r in current}
        if complete:
            for object_id in sorted(self._known_objects - current_ids):
                pairs.append(self._envelope(NangoRecord(object_id, {}, 1, Operation.DELETE), run_id=run_id))
        return AdapterBatch(None, tuple(pairs), complete, run_id, capability=self.capability,
                            capability_status=CapabilityStatus.COMPLETE if complete else CapabilityStatus.PARTIAL)
