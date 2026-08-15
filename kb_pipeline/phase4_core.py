"""Phase 4 core contracts and PostgreSQL-shaped reference implementations.

Scope is deliberately development/mock: callers inject psycopg connections and
Principal providers. No authentication or cloud implementation lives here.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Mapping, Sequence

from .domain import ACL, CanonicalDocument
from .security import AuthorizationError, Principal


def _stamp(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


def _jsonb(value: Mapping[str, Any]):
    """Adapt JSON only when PostgreSQL path is actually used."""
    try:
        from psycopg.types.json import Jsonb
    except ImportError:
        return json.dumps(value)
    return Jsonb(value)


@dataclass(frozen=True, order=True)
class SemanticIdentity:
    tenant: str
    source: str
    source_id: str

    def __post_init__(self):
        if not all(isinstance(v, str) and v for v in (self.tenant, self.source, self.source_id)):
            raise ValueError("semantic identity fields are required")

    @property
    def key(self) -> tuple[str, str, str]:
        return self.tenant, self.source, self.source_id


class IdentityCollision(ValueError):
    pass


def resolve_legacy_identity(*, tenant: str, object_id: str, source: str | None = None,
                            provider: str = "", connector: str = "", source_instance: str = "") -> SemanticIdentity:
    """Explicit legacy mapping. Provenance fields must never silently redefine key."""
    semantic_source = source or connector or source_instance or provider
    if not semantic_source:
        raise ValueError("legacy identity requires explicit source mapping")
    return SemanticIdentity(tenant, semantic_source, object_id)


class IdentityRegistry:
    """Fail-closed semantic-key registry retaining provenance aliases."""
    def __init__(self):
        self._keys: dict[SemanticIdentity, tuple[str, str, str]] = {}

    def register(self, identity: SemanticIdentity, *, provider: str = "", connector: str = "",
                 source_instance: str = "") -> SemanticIdentity:
        provenance = (provider, connector, source_instance)
        old = self._keys.get(identity)
        if old is not None and old != provenance:
            raise IdentityCollision(f"semantic identity collision: {identity.key}")
        self._keys[identity] = provenance
        return identity


class EnvelopeOperation(str, Enum):
    UPSERT = "upsert"
    DELETE = "delete"
    PERMISSION = "permission-change"


@dataclass(frozen=True)
class ReplayEnvelope:
    event_id: str
    idempotency_key: str
    semantic_key: SemanticIdentity
    revision: int
    operation: EnvelopeOperation
    payload: Mapping[str, Any] | None
    raw_reference: Mapping[str, str] | None
    provenance: Mapping[str, str]
    permissions: Mapping[str, Any]
    correlation_id: str
    observed_at: datetime
    protocol_version: str = "p4-envelope.v1"

    def __post_init__(self):
        if self.revision < 1 or not self.event_id or not self.idempotency_key or not self.correlation_id:
            raise ValueError("invalid replay envelope")

    def as_dict(self) -> dict[str, Any]:
        return {"protocol_version": self.protocol_version, "event_id": self.event_id,
                "idempotency_key": self.idempotency_key, "semantic_key": self.semantic_key.key,
                "revision": self.revision, "operation": self.operation.value,
                "payload": self.payload, "raw_reference": self.raw_reference,
                "provenance": dict(self.provenance), "permissions": dict(self.permissions),
                "correlation_id": self.correlation_id, "observed_at": _stamp(self.observed_at)}

    def serialize(self) -> str:
        return json.dumps(self.as_dict(), sort_keys=True, separators=(",", ":"))

    @classmethod
    def deserialize(cls, value: str | Mapping[str, Any]) -> "ReplayEnvelope":
        item = json.loads(value) if isinstance(value, str) else dict(value)
        tenant, source, source_id = item["semantic_key"]
        return cls(item["event_id"], item["idempotency_key"], SemanticIdentity(tenant, source, source_id),
                   int(item["revision"]), EnvelopeOperation(item["operation"]), item.get("payload"),
                   item.get("raw_reference"), item.get("provenance", {}), item.get("permissions", {}),
                   item["correlation_id"], datetime.fromisoformat(item["observed_at"]), item.get("protocol_version", ""))


class BarrierState(str, Enum):
    FRESH = "fresh"
    PENDING = "pending"
    STALE = "stale"
    BLOCKED = "blocked"
    TIMEOUT = "timeout"


@dataclass(frozen=True)
class ProjectionWatermark:
    accepted_sequence: int
    applied_sequence: int
    state: BarrierState


class ProjectionBarrier:
    def __init__(self, *, accepted: int = 0, applied: int = 0, blocked: bool = False):
        self.accepted, self.applied, self.blocked = accepted, applied, blocked

    def observe(self, min_sequence: int = 0, timeout: bool = False) -> ProjectionWatermark:
        if timeout: state = BarrierState.TIMEOUT
        elif self.blocked: state = BarrierState.BLOCKED
        elif self.applied < min_sequence: state = BarrierState.PENDING
        elif self.applied < self.accepted: state = BarrierState.STALE
        else: state = BarrierState.FRESH
        return ProjectionWatermark(self.accepted, self.applied, state)

    def require(self, min_sequence: int, *, timeout: bool = False, eventual: bool = False) -> ProjectionWatermark:
        result = self.observe(min_sequence, timeout=timeout)
        if result.state in {BarrierState.PENDING, BarrierState.STALE, BarrierState.BLOCKED, BarrierState.TIMEOUT} and not (eventual and result.state == BarrierState.STALE):
            raise TimeoutError(f"projection barrier {result.state.value}")
        return result


class PostgresProjectionWorker:
    """Idempotent projection worker. Authority remains ingestion_authority."""
    def __init__(self, connection, *, projection: str = "document", failure: Callable[[ReplayEnvelope], None] | None = None):
        if not re.fullmatch(r"[a-z_]+", projection): raise ValueError("invalid projection name")
        self.connection, self.projection, self.failure = connection, projection, failure

    def apply(self, envelope: ReplayEnvelope) -> None:
        if self.failure: self.failure(envelope)
        key = envelope.semantic_key
        provenance = envelope.provenance
        required = ("provider", "connector", "source_instance")
        if any(not isinstance(provenance.get(field), str) or not provenance[field] for field in required) or provenance["connector"] != key.source:
            raise IdentityCollision("explicit source namespace mapping required")
        alias = (key.tenant, key.source, key.source_id, provenance["provider"], provenance["connector"], provenance["source_instance"])
        self.connection.execute("INSERT INTO p4_identity_aliases (tenant,source,source_id,provider,connector,source_instance) VALUES (%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING", alias)
        existing = self.connection.execute("SELECT provider,connector,source_instance FROM p4_identity_aliases WHERE tenant=%s AND source=%s AND source_id=%s", key.key).fetchone()
        if tuple(existing or ()) != alias[3:]:
            raise IdentityCollision(f"source namespace collision: {key.key}")
        tombstone = self.connection.execute("SELECT tombstoned FROM p4_document WHERE tenant=%s AND source=%s AND source_id=%s", key.key).fetchone()
        if tombstone and tombstone[0] and envelope.operation != EnvelopeOperation.DELETE:
            return
        payload = envelope.payload or {}
        acl = envelope.permissions
        self.connection.execute(f"""INSERT INTO p4_{self.projection}
          (tenant,source,source_id,revision,operation,title,body,raw_reference,content_hash,
           provenance,readers,admins,tombstoned,semantic_key,updated_at)
          VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
          ON CONFLICT (tenant,source,source_id) DO UPDATE SET
            revision=EXCLUDED.revision,operation=EXCLUDED.operation,title=EXCLUDED.title,
            body=EXCLUDED.body,raw_reference=EXCLUDED.raw_reference,content_hash=EXCLUDED.content_hash,
            provenance=EXCLUDED.provenance,readers=EXCLUDED.readers,admins=EXCLUDED.admins,
            tombstoned=EXCLUDED.tombstoned,updated_at=EXCLUDED.updated_at
          WHERE p4_{self.projection}.revision < EXCLUDED.revision""",
          (key.tenant, key.source, key.source_id, envelope.revision, envelope.operation.value,
           payload.get("title", ""), payload.get("text", ""), _jsonb(envelope.raw_reference or {}),
           (envelope.raw_reference or {}).get("content_hash", ""), _jsonb(envelope.provenance),
           acl.get("readers"), acl.get("admins", []), envelope.operation == EnvelopeOperation.DELETE,
           json.dumps(key.key), envelope.observed_at))

    def apply_at_sequence(self, sequence: int, envelope: ReplayEnvelope) -> None:
        """Apply projection and watermark in one caller-owned transaction."""
        self.apply(envelope)
        current = self.connection.execute("SELECT sequence FROM p4_projection_checkpoints WHERE projection=%s FOR UPDATE", (self.projection,)).fetchone()
        expected = int(current[0]) + 1 if current else 1
        if sequence != expected:
            raise ValueError(f"projection checkpoint requires sequence {expected}, got {sequence}")
        self.connection.execute("""INSERT INTO p4_projection_checkpoints(projection,sequence,state)
          VALUES (%s,%s,'fresh') ON CONFLICT (projection) DO UPDATE
          SET sequence=EXCLUDED.sequence,
              state='fresh', last_error=NULL, updated_at=now()""", (self.projection, sequence))


@dataclass(frozen=True)
class QueryResultDTO:
    identity: SemanticIdentity
    revision: int
    score: float
    title: str
    snippet: str
    provenance: Mapping[str, str]
    citation: Mapping[str, Any]


class PostgresFTSQueryService:
    def __init__(self, connection, *, barrier: ProjectionBarrier | None = None):
        self.connection, self.barrier = connection, barrier or ProjectionBarrier()

    def search(self, principal: Principal, text: str, *, limit: int = 20, min_sequence: int = 0,
               source: str = "", timeout: bool = False, eventual: bool = False) -> tuple[QueryResultDTO, ...]:
        if not principal.can_read(principal.tenant, source): raise AuthorizationError("tenant/source denied")
        if not 1 <= limit <= 100: raise ValueError("limit must be between 1 and 100")
        if not text.strip(): return ()
        self.barrier.require(min_sequence, timeout=timeout, eventual=eventual)
        # ACL and tenant predicates precede rank and LIMIT by design.
        rows = self.connection.execute("""SELECT tenant,source,source_id,revision,ts_rank(search_vector, plainto_tsquery('simple', %s)) AS score,
          title, ts_headline('simple', body, plainto_tsquery('simple', %s)) AS snippet, provenance,raw_reference
          FROM p4_document WHERE tenant=%s AND tombstoned=false AND readers IS NOT NULL AND %s = ANY(readers)
            AND (%s='' OR source=%s) AND search_vector @@ plainto_tsquery('simple', %s)
          ORDER BY score DESC, source_id LIMIT %s""",
          (text, text, principal.tenant, principal.subject, source, source, text, limit)).fetchall()
        return tuple(QueryResultDTO(SemanticIdentity(r[0], r[1], r[2]), r[3], float(r[4]), r[5], r[6], r[7],
                                     {"raw_reference": r[8], "revision": r[3]}) for r in rows)


def verify_citation(connection, principal: Principal, result: QueryResultDTO) -> bool:
    if not principal.can_read(result.identity.tenant, result.identity.source): return False
    row = connection.execute("""SELECT revision,content_hash,tombstoned,readers FROM p4_document
      WHERE tenant=%s AND source=%s AND source_id=%s""", result.identity.key).fetchone()
    if not row or row[0] != result.revision or row[2] or (row[3] is None or principal.subject not in row[3]):
        return False
    reference = result.citation.get("raw_reference", {})
    if (not isinstance(reference, Mapping) or not reference.get("uri") or
            not isinstance(reference.get("content_hash"), str) or
            not reference["content_hash"] or row[1] != reference["content_hash"]):
        return False
    # Authority verification is mandatory; projection-only evidence abstains.
    try:
        p = result.provenance
        authority = connection.execute("""SELECT revision,raw_object_uri,content_hash,operation
          FROM ingestion_authority WHERE provider=%s AND tenant=%s AND connector=%s
          AND source_instance=%s AND object_id=%s""",
          (p["provider"], result.identity.tenant, p["connector"], p["source_instance"],
           result.identity.source_id)).fetchone()
    except Exception:
        return False
    return bool(authority and authority[0] == result.revision and
                authority[1] == reference["uri"] and authority[2] == reference["content_hash"] and
                authority[3] != "delete")
