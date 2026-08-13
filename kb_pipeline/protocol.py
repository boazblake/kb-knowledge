"""Provider-neutral Phase 4 protocol spine.

This module contains contracts and small reference implementations. Provider SDKs
must stop at Connector/Canonicalizer boundaries.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
import hmac
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from enum import Enum
from typing import Any, Iterable, Mapping, Protocol, Sequence

from .domain import ACL, CanonicalDocument, RawRecord, SearchHit


def _now() -> datetime: return datetime.now(timezone.utc)
def _stamp(value: datetime) -> str: return value.isoformat()


def freshness_status(observed_at: datetime, *, external: bool = False, now: datetime | None = None) -> str:
    age = (now or _now()) - observed_at
    limit = 900 if external else 300
    return "fresh" if age.total_seconds() <= limit else "stale"


class Operation(str, Enum):
    UPSERT = "upsert"
    DELETE = "delete"
    PERMISSION = "permission-change"


@dataclass(frozen=True)
class IdentityNamespace:
    provider: str
    tenant: str = "default"
    subject: str = ""
    connector: str = ""
    source_instance: str = ""

    @property
    def key(self) -> str:
        return json.dumps((self.provider, self.tenant, self.subject,
                           self.connector, self.source_instance), separators=(",", ":"))


@dataclass(frozen=True)
class ObjectKey:
    provider: str
    tenant: str
    connector: str
    source_instance: str
    object: str

    @classmethod
    def from_change(cls, change):
        return cls(change.source.provider, change.source.tenant,
                   change.source.connector,
                   change.source.source_instance,
                   change.object_id)

    def encoded(self): return json.dumps((self.provider, self.tenant, self.connector, self.source_instance, self.object))
    def tuple(self): return (self.provider, self.tenant, self.connector, self.source_instance, self.object)


class RevisionOutcome(str, Enum):
    ACCEPTED = "accepted"
    DUPLICATE = "duplicate"
    STALE = "stale"
    CONFLICT = "conflict"
    GAP = "gap"


class KeyProvider(Protocol):
    def encrypt(self, plaintext: bytes, *, key_id: str): ...
    def decrypt(self, envelope): ...


@dataclass(frozen=True)
class PayloadEnvelope:
    key_id: str
    algorithm: str
    ciphertext: bytes
    nonce: bytes
    tag: bytes


class LocalTestKeyProvider:
    """Safe test-only adapter. Production requires injected external KMS."""
    test_only = True
    def __init__(self, key=b"local-test-key-32-bytes---------"): self.key = key
    def encrypt(self, plaintext, *, key_id):
        nonce = hashlib.sha256(self.key + plaintext).digest()[:16]
        stream = hashlib.sha256(self.key + nonce).digest()
        ciphertext = bytes(x ^ stream[i % len(stream)] for i, x in enumerate(plaintext))
        return PayloadEnvelope(key_id, "TEST-XOR-HMAC", ciphertext, nonce, hmac.new(self.key, nonce + ciphertext, hashlib.sha256).digest())
    def decrypt(self, envelope):
        expected = hmac.new(self.key, envelope.nonce + envelope.ciphertext, hashlib.sha256).digest()
        if envelope.algorithm != "TEST-XOR-HMAC" or not hmac.compare_digest(expected, envelope.tag): raise ValueError("invalid payload envelope")
        stream = hashlib.sha256(self.key + envelope.nonce).digest()
        return bytes(x ^ stream[i % len(stream)] for i, x in enumerate(envelope.ciphertext))


@dataclass(frozen=True)
class PermissionState:
    acl: ACL
    resolved: bool = True
    observed_at: datetime = field(default_factory=_now)

    def permits(self, identity: IdentityNamespace | str, is_admin: bool = False) -> bool:
        return self.acl.permits(identity.key if isinstance(identity, IdentityNamespace) else identity, is_admin)


@dataclass(frozen=True)
class ProvenanceLink:
    kind: str
    identifier: str
    parent: "ProvenanceLink | None" = None

    def chain(self) -> tuple["ProvenanceLink", ...]:
        return (self,) + (() if self.parent is None else self.parent.chain())


@dataclass(frozen=True)
class Envelope:
    envelope_id: str
    protocol_version: str
    emitted_at: datetime
    source: IdentityNamespace
    idempotency_key: str
    payload: Any
    trace_id: str = ""


@dataclass(frozen=True)
class CanonicalChange:
    object_id: str
    source: IdentityNamespace
    revision: int
    operation: Operation
    value: CanonicalDocument | Mapping[str, Any] | None
    idempotency_key: str
    provenance: ProvenanceLink
    permissions: PermissionState
    data_class: str = "default"
    occurred_at: datetime = field(default_factory=_now)


@dataclass(frozen=True)
class DataPurgePolicy:
    retention: Mapping[str, bool] = field(default_factory=lambda: {"default": False})

    def purge_allowed(self, data_class: str) -> bool: return self.retention.get(data_class, self.retention.get("default", False))


class Ledger(Protocol):
    def append(self, change: CanonicalChange) -> bool: ...
    def changes(self, after: int = 0) -> Iterable[CanonicalChange]: ...
    def revision(self, source: IdentityNamespace, object_id: str) -> int: ...
    def checkpoint(self, stream: str) -> int: ...
    def save_checkpoint(self, stream: str, sequence: int) -> None: ...


class KnowledgeStore(Protocol):
    def apply(self, change: CanonicalChange) -> bool: ...
    def current(self, object_id: str) -> CanonicalChange | None: ...
    def purge(self, object_id: str, data_class: str) -> bool: ...


class Projection(Protocol):
    name: str
    def apply(self, change: CanonicalChange) -> None: ...
    def remove(self, object_id: str) -> None: ...


class Retriever(Protocol):
    def search(self, query: "Query") -> "QueryResult": ...


@dataclass(frozen=True)
class Query:
    text: str
    identity: IdentityNamespace | str
    is_admin: bool = False
    limit: int = 20
    source: IdentityNamespace | None = None

    def __post_init__(self):
        if not 1 <= self.limit <= 100: raise ValueError("limit must be between 1 and 100")


@dataclass(frozen=True)
class Evidence:
    hit: SearchHit
    provenance: tuple[ProvenanceLink, ...]
    revision: int


@dataclass(frozen=True)
class QueryResult:
    evidence: tuple[Evidence, ...]
    complete: bool = True


class RelationalReferenceLedger:
    """Append-only SQLite reference ledger. One sequence gives deterministic replay."""
    def __init__(self, db: sqlite3.Connection):
        self.db = db
        self._lock = threading.RLock()
        # All durable protocol writes share this lock. Readers do not.
        self.writer_lock = self._lock
        self.db.execute("CREATE TABLE IF NOT EXISTS protocol_ledger (sequence INTEGER PRIMARY KEY AUTOINCREMENT, idempotency TEXT UNIQUE, object_id TEXT, source TEXT, revision INTEGER, operation TEXT, payload TEXT, provenance TEXT, permissions TEXT, data_class TEXT, occurred_at TEXT, object_key TEXT, source_version TEXT)")
        self.db.execute("CREATE TABLE IF NOT EXISTS protocol_conflicts (sequence INTEGER PRIMARY KEY AUTOINCREMENT, tenant TEXT, object_id TEXT, revision INTEGER, idempotency TEXT, reason TEXT, payload TEXT, occurred_at TEXT)")
        self.db.execute("CREATE TABLE IF NOT EXISTS protocol_checkpoints (stream TEXT PRIMARY KEY, sequence INTEGER NOT NULL)")
        self.db.execute("CREATE TABLE IF NOT EXISTS protocol_outbox (sequence INTEGER PRIMARY KEY, status TEXT NOT NULL DEFAULT 'pending', claimed_by TEXT, lease_until TEXT, attempts INTEGER NOT NULL DEFAULT 0, max_attempts INTEGER NOT NULL DEFAULT 5, last_error TEXT, FOREIGN KEY(sequence) REFERENCES protocol_ledger(sequence))")
        self.db.execute("CREATE TABLE IF NOT EXISTS protocol_dead_letters (sequence INTEGER PRIMARY KEY, reason TEXT NOT NULL, failed_at TEXT NOT NULL)")
        self.db.execute("CREATE TABLE IF NOT EXISTS protocol_gaps (id INTEGER PRIMARY KEY AUTOINCREMENT, object_key TEXT, expected INTEGER, received INTEGER, idempotency TEXT UNIQUE, payload TEXT, occurred_at TEXT)")
        try: self.db.execute("ALTER TABLE protocol_ledger ADD COLUMN object_key TEXT")
        except sqlite3.OperationalError: pass
        try: self.db.execute("ALTER TABLE protocol_ledger ADD COLUMN source_version TEXT")
        except sqlite3.OperationalError: pass
        self.db.commit()

    def append(self, change: CanonicalChange) -> bool:
        return self.append_outcome(change) == RevisionOutcome.ACCEPTED

    def append_outcome(self, change: CanonicalChange) -> RevisionOutcome:
        with self._lock:
            return self._append_outcome(change)

    def _append_outcome(self, change: CanonicalChange) -> RevisionOutcome:
        if change.revision <= 0: raise ValueError("revision must be positive")
        payload = change.value
        if isinstance(payload, CanonicalDocument):
            payload = {"document_id": payload.document_id, "title": payload.title, "text": payload.text, "source_uri": payload.source.source_uri, "metadata": dict(payload.metadata)}
        payload_json = json.dumps(payload, default=str)
        fingerprint = json.dumps((change.source.tenant, change.object_id, change.revision, change.operation.value, payload), sort_keys=True, default=str)
        object_key = ObjectKey.from_change(change).encoded()
        source_json = json.dumps((change.source.provider, change.source.tenant,
                                  change.source.subject, change.source.connector,
                                  change.source.source_instance), separators=(",", ":"))
        existing = self.db.execute("SELECT payload, object_id, source, revision, operation, idempotency FROM protocol_ledger WHERE idempotency=? OR (object_key=? AND revision=?)", (change.idempotency_key, object_key, change.revision)).fetchone()
        if existing:
            same = (existing[5] == change.idempotency_key and existing[2] == source_json and
                    existing[3] == change.revision and existing[4] == change.operation.value and
                    existing[0] == payload_json)
            if not same:
                self.db.execute("INSERT INTO protocol_conflicts(tenant,object_id,revision,idempotency,reason,payload,occurred_at) VALUES (?,?,?,?,?,?,?)", (change.source.tenant, change.object_id, change.revision, change.idempotency_key, "conflicting-payload-or-idempotency", fingerprint, _stamp(change.occurred_at)))
                self.db.commit(); return RevisionOutcome.CONFLICT
            return RevisionOutcome.DUPLICATE
        current = self.db.execute("SELECT max(revision) FROM protocol_ledger WHERE object_key=?", (object_key,)).fetchone()[0] or 0
        if current >= change.revision: return RevisionOutcome.STALE
        if change.revision > current + 1:
            self.db.execute("INSERT OR IGNORE INTO protocol_gaps(object_key,expected,received,idempotency,payload,occurred_at) VALUES (?,?,?,?,?,?)", (object_key, current + 1, change.revision, change.idempotency_key, fingerprint, _stamp(change.occurred_at)))
            self.db.commit(); return RevisionOutcome.GAP
        try:
            provenance = [{"kind": x.kind, "identifier": x.identifier} for x in change.provenance.chain()]
            source_version = None if not isinstance(change.value, CanonicalDocument) else json.dumps({"source_id": change.value.source.source_id, "version": change.value.source.version, "source_uri": change.value.source.source_uri, "observed_at": _stamp(change.value.source.observed_at), "content_hash": change.value.source.content_hash, "supersedes": change.value.source.supersedes}, sort_keys=True)
            permissions = {"readers": list(change.permissions.acl.readers) if change.permissions.acl.readers is not None else None,
                          "admins": list(change.permissions.acl.admins),
                          "resolved": change.permissions.resolved,
                          "observed_at": _stamp(change.permissions.observed_at)}
            self.db.execute("INSERT INTO protocol_ledger(idempotency,object_id,source,revision,operation,payload,provenance,permissions,data_class,occurred_at,object_key,source_version) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", (change.idempotency_key, change.object_id, source_json, change.revision, change.operation.value, payload_json, json.dumps(provenance), json.dumps(permissions), change.data_class, _stamp(change.occurred_at), object_key, source_version))
            self.db.execute("INSERT INTO protocol_outbox(sequence) VALUES (last_insert_rowid())")
            self.db.commit(); return RevisionOutcome.ACCEPTED
        except sqlite3.IntegrityError:
            self.db.rollback(); return RevisionOutcome.DUPLICATE

    def changes(self, after=0):
        return tuple(self._decode(row) for row in self.db.execute("SELECT * FROM protocol_ledger WHERE sequence>? ORDER BY sequence", (after,)))

    def _decode(self, row):
        acl = json.loads(row[8]); source = IdentityNamespace(*json.loads(row[3])); links = json.loads(row[7]); parent = None
        for link in reversed(links): parent = ProvenanceLink(link["kind"], link["identifier"], parent)
        payload = json.loads(row[6])
        value = None
        if payload is not None and Operation(row[5]) != Operation.DELETE:
            from .domain import SourceVersion
            sv_data = json.loads(row[12]) if row[12] else {"source_id": row[2], "version": str(row[4]), "source_uri": payload.get("source_uri", ""), "observed_at": row[10], "content_hash": payload.get("content_hash", "")}
            sv = SourceVersion(sv_data["source_id"], sv_data["version"], sv_data["source_uri"], datetime.fromisoformat(sv_data["observed_at"]), sv_data["content_hash"], sv_data.get("supersedes"))
            value = CanonicalDocument(row[2], sv, payload.get("title", row[2]), payload.get("text", ""), ACL(None if acl["readers"] is None else frozenset(acl["readers"]), frozenset(acl["admins"])), payload.get("metadata", {}))
        permissions = PermissionState(ACL(None if acl["readers"] is None else frozenset(acl["readers"]), frozenset(acl["admins"])),
                                      acl.get("resolved", True), datetime.fromisoformat(acl["observed_at"]) if acl.get("observed_at") else _now())
        return CanonicalChange(row[2], source, row[4], Operation(row[5]), value, row[1], parent or ProvenanceLink("unknown", row[2]), permissions, row[9], datetime.fromisoformat(row[10]))

    def revision(self, source, object_id):
        object_key = ObjectKey(source.provider, source.tenant, source.connector,
                               source.source_instance, object_id).encoded()
        row = self.db.execute("SELECT max(revision) FROM protocol_ledger WHERE object_key=?", (object_key,)).fetchone(); return row[0] or 0
    def revision_for_idempotency(self, key):
        row = self.db.execute("SELECT revision FROM protocol_ledger WHERE idempotency=?", (key,)).fetchone()
        return row[0] if row else None
    def conflicts(self):
        return tuple(self.db.execute("SELECT tenant, object_id, revision, idempotency, reason FROM protocol_conflicts ORDER BY sequence"))
    @property
    def conflict_count(self):
        return self.db.execute("SELECT count(*) FROM protocol_conflicts").fetchone()[0]
    def gaps(self): return tuple(self.db.execute("SELECT object_key,expected,received,idempotency FROM protocol_gaps ORDER BY id"))
    def outbox(self, after=0): return tuple(self.db.execute("SELECT sequence,status FROM protocol_outbox WHERE sequence>? ORDER BY sequence", (after,)))
    def claim_outbox(self, worker: str, now: datetime | None = None, lease_seconds: int = 60, limit: int = 100):
        now = now or _now(); stamp = _stamp(now); expiry = _stamp(now + timedelta(seconds=lease_seconds))
        with self._lock:
            self.db.execute("UPDATE protocol_outbox SET status='pending', claimed_by=NULL, lease_until=NULL WHERE status='claimed' AND lease_until<?", (stamp,))
            rows = self.db.execute("SELECT sequence FROM protocol_outbox WHERE status='pending' ORDER BY sequence LIMIT ?", (limit,)).fetchall()
            for row in rows: self.db.execute("UPDATE protocol_outbox SET status='claimed',claimed_by=?,lease_until=?,attempts=attempts+1 WHERE sequence=?", (worker, expiry, row[0]))
            self.db.commit(); return tuple(r[0] for r in rows)
    def mark_applied(self, sequence: int, worker: str):
        self.db.execute("UPDATE protocol_outbox SET status='applied',claimed_by=NULL,lease_until=NULL WHERE sequence=? AND status='claimed' AND claimed_by=?", (sequence, worker)); self.db.commit()
    def mark_failed(self, sequence: int, worker: str, error: str):
        row = self.db.execute("SELECT attempts,max_attempts FROM protocol_outbox WHERE sequence=? AND claimed_by=?", (sequence, worker)).fetchone()
        if not row: return
        terminal = row[0] >= row[1]
        self.db.execute("UPDATE protocol_outbox SET status='failed',claimed_by=NULL,lease_until=NULL,last_error=? WHERE sequence=?", (error, sequence))
        if terminal: self.db.execute("INSERT OR REPLACE INTO protocol_dead_letters VALUES (?,?,?)", (sequence, error, _stamp(_now())))
        else: self.db.execute("UPDATE protocol_outbox SET status='pending' WHERE sequence=?", (sequence,))
        self.db.commit()
    def dead_letters(self): return tuple(self.db.execute("SELECT sequence,reason,failed_at FROM protocol_dead_letters ORDER BY sequence"))
    def checkpoint(self, stream):
        row = self.db.execute("SELECT sequence FROM protocol_checkpoints WHERE stream=?", (stream,)).fetchone(); return row[0] if row else 0
    def save_checkpoint(self, stream, sequence):
        self.db.execute("INSERT OR REPLACE INTO protocol_checkpoints VALUES (?,?)", (stream, sequence)); self.db.commit()


class CurrentStateStore:
    def __init__(self): self._state: dict[tuple, CanonicalChange] = {}
    @staticmethod
    def _key(source, object_id):
        if isinstance(source, IdentityNamespace): return ObjectKey(source.provider, source.tenant, source.connector, source.source_instance, object_id).tuple()
        return (str(source), object_id)
    def apply(self, change):
        old = self._state.get(self._key(change.source, change.object_id))
        if old and (change.revision <= old.revision or old.operation == Operation.DELETE): return False
        self._state[self._key(change.source, change.object_id)] = change; return True
    def current(self, object_id, source=None):
        if source is not None: return self._state.get(self._key(source, object_id))
        # Legacy lookup; never merges namespaces. Deterministic first match only.
        return next((v for key, v in self._state.items() if key[-1] == object_id), None)
    def purge(self, object_id, data_class, source=None):
        keys = [self._key(source, object_id)] if source is not None else [k for k in self._state if k[-1] == object_id]
        for key in keys: self._state.pop(key, None)
        return bool(keys)


class StateProjection:
    name = "state"
    def __init__(self): self.values = {}; self.revisions = {}; self.tombstones = set()
    @staticmethod
    def _key(change): return ObjectKey.from_change(change).tuple()
    def apply(self, change):
        key = self._key(change)
        if change.revision <= self.revisions.get(key, 0): return
        self.revisions[key] = change.revision
        if change.operation == Operation.DELETE:
            self.values.pop(key, None); self.tombstones.add(key)
        elif change.value is not None and key not in self.tombstones: self.values[key] = change.value
    def remove(self, object_id, source=None):
        if source is None:
            for key in [k for k in self.values if k[-1] == object_id]: self.values.pop(key, None)
        else: self.values.pop(ObjectKey.from_change(CanonicalChange(object_id, source, 0, Operation.DELETE, None, "", ProvenanceLink("purge", object_id), PermissionState(ACL(None)))).tuple(), None)


class DocumentProjection(StateProjection): name = "document"
class RelationshipProjection(StateProjection): name = "relationship"


class LexicalProjection:
    name = "lexical"
    def __init__(self, index, visible=None): self.index = index; self.visible = visible or (lambda change: True); self.revisions = {}; self.tombstones = set()
    def apply(self, change):
        key = ObjectKey.from_change(change).tuple()
        if change.revision <= self.revisions.get(key, 0): return
        if change.operation == Operation.DELETE: self.tombstones.add(key)
        if key in self.tombstones and change.operation != Operation.DELETE: return
        if change.operation == Operation.DELETE or change.permissions.acl.readers is None: self.index.remove(change.object_id, change.source)
        elif isinstance(change.value, CanonicalDocument) and self.visible(change):
            try: self.index.replace(change.value, change.source)
            except TypeError: self.index.replace(change.value)
        self.revisions[key] = change.revision
    def remove(self, object_id, source=None): self.index.remove(object_id, source)


class KnowledgeEngine:
    def __init__(self, ledger, store, projections=(), checkpoint_stream="default"):
        self.ledger, self.store, self.projections, self.stream = ledger, store, tuple(projections), checkpoint_stream
        self._writer = getattr(ledger, "writer_lock", threading.RLock())
    def append(self, change):
        outcome = self.ledger.append_outcome(change) if hasattr(self.ledger, "append_outcome") else (RevisionOutcome.ACCEPTED if self.ledger.append(change) else RevisionOutcome.DUPLICATE)
        return outcome
    def apply(self, change):
        with self._writer:
            current = self.store.current(change.object_id, change.source) if hasattr(self.store, "current") else None
            if current is not None and current.operation == Operation.DELETE: return False
            outcome = self.append(change)
            if outcome == RevisionOutcome.DUPLICATE:
                self.process_outbox(worker="engine", failure=None)
                return False
            if outcome != RevisionOutcome.ACCEPTED: return False
            self.process_outbox(worker="engine", failure=None, raise_on_failure=True)
            return True
    def _apply_store(self, change):
        if hasattr(self.store, "apply"):
            return self.store.apply(change)
        if change.operation == Operation.DELETE:
            self.store.tombstone(change.object_id)
            return True
        return self.store.put(change.value)
    def replay(self, rebuild=False):
        with self._writer:
            targets = (("state", self.store), *[(p.name, p) for p in self.projections])
            for name, target in targets:
                after = 0 if rebuild else self.ledger.checkpoint(f"{self.stream}:{name}")
                rows = self.ledger.changes(after)
                expected = after + 1
                for change in rows:
                    sequence = self._sequence(change)
                    if sequence != expected: raise ValueError(f"ledger sequence gap: expected {expected}, got {sequence}")
                    if name == "state": self._apply_store(change)
                    else: target.apply(change)
                    self.ledger.save_checkpoint(f"{self.stream}:{name}", sequence)
                    expected += 1
            return True
    def process_outbox(self, worker="engine", failure=None, raise_on_failure=False):
        for sequence in self.ledger.claim_outbox(worker):
            change = next((item for item in self.ledger.changes() if self._sequence(item) == sequence), None)
            try:
                if failure: failure(sequence, change)
                if change is not None:
                    stored = self._apply_store(change)
                    current = self.store.current(change.object_id, change.source) if hasattr(self.store, "current") else None
                    durable = current is not None and current.idempotency_key == change.idempotency_key
                    if hasattr(self.store, "get") and isinstance(change.value, CanonicalDocument):
                        existing = self.store.get(change.object_id)
                        durable = existing is not None and existing.source.content_hash == change.value.source.content_hash
                    if stored or durable:
                        for projection in self.projections: projection.apply(change)
                self.ledger.mark_applied(sequence, worker)
            except Exception as exc:
                self.ledger.mark_failed(sequence, worker, str(exc))
                if raise_on_failure: raise
        return True
    def _sequence(self, change):
        # Sequence is durable ledger ordering; caller may use changes(after) for batching.
        return next(row[0] for row in self.ledger.db.execute("SELECT sequence FROM protocol_ledger WHERE idempotency=?", (change.idempotency_key,)))
    def checkpoint(self):
        with self._writer:
            sequence = len(tuple(self.ledger.changes()))
            for name in ("state", *(p.name for p in self.projections)):
                self.ledger.save_checkpoint(f"{self.stream}:{name}", sequence)
    def purge(self, object_id, source, data_class="default", policy=None):
        if policy is not None and not policy.purge_allowed(data_class):
            return {"object_id": object_id, "tenant_id": source.tenant, "purged": False, "reason": "retention-policy"}
        self.store.purge(object_id, data_class, source)
        for projection in self.projections: projection.remove(object_id, source)
        return {"object_id": object_id, "tenant_id": source.tenant, "purged": True, "derived_projection": "removed"}


@dataclass(frozen=True)
class CapabilityDescriptor:
    name: str
    version: str
    features: frozenset[str] = frozenset()

    def compatible_with(self, required): return self.name == required.name and self.version.split(".")[0] == required.version.split(".")[0] and required.features <= self.features


@dataclass(frozen=True)
class CompositionManifest:
    components: Mapping[str, CapabilityDescriptor]
    required: Mapping[str, CapabilityDescriptor] = field(default_factory=dict)

    def validate(self):
        missing = [k for k, req in self.required.items() if k not in self.components or not self.components[k].compatible_with(req)]
        if missing: raise ValueError("incompatible components: " + ", ".join(missing))
        return True
