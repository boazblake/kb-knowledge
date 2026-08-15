"""PostgreSQL authority adapter.

Psycopg owns pooling, parameter binding, and transaction boundaries. This module
contains no workflow engine or provider SDK implementation.
"""
from __future__ import annotations

import contextlib
import json
import re
from pathlib import Path
from typing import Any, Iterator, cast

from .protocol import CanonicalChange, IdentityNamespace, ObjectKey, RevisionOutcome


class PostgresUnavailable(RuntimeError):
    """Required PostgreSQL driver or database is unavailable."""


def _driver():
    try:
        import psycopg
        from psycopg_pool import ConnectionPool
    except ImportError as exc:  # fail closed; never silently use SQLite
        raise PostgresUnavailable("psycopg[binary,pool] is required for PostgreSQL authority") from exc
    return psycopg, ConnectionPool


class MigrationRunner:
    def __init__(self, migrations_dir: str | Path | None = None):
        self.directory = Path(migrations_dir or Path(__file__).resolve().parent.parent / "migrations")

    def run(self, connection) -> tuple[int, ...]:
        connection.execute("CREATE TABLE IF NOT EXISTS schema_migrations (version integer PRIMARY KEY, applied_at timestamptz NOT NULL DEFAULT now())")
        applied = {row[0] for row in connection.execute("SELECT version FROM schema_migrations").fetchall()}
        versions: list[int] = []
        for path in sorted(self.directory.glob("*.sql")):
            match = re.match(r"^(\d+)_", path.name)
            if not match:
                raise ValueError(f"invalid migration filename: {path.name}")
            version = int(match.group(1))
            if version in applied:
                continue
            connection.execute(path.read_text(encoding="utf-8"))
            connection.execute("INSERT INTO schema_migrations(version) VALUES (%s)", (version,))
            versions.append(version)
        return tuple(versions)


class PostgresAuthorityRepository:
    """Transactional authority for connector identity, revisions and delivery."""
    test_only = False

    def __init__(self, dsn: str, *, pool: Any = None, migrations_dir: str | Path | None = None,
                 min_size: int = 1, max_size: int = 10):
        if not dsn.startswith(("postgres://", "postgresql://")):
            raise ValueError("PostgreSQL DSN required")
        self.dsn = dsn
        if pool is None:
            _, pool_type = _driver()
            pool = pool_type(conninfo=dsn, min_size=min_size, max_size=max_size, open=False)
        self.pool = pool
        self.migrations = MigrationRunner(migrations_dir)

    def open(self):
        self.pool.open(wait=True)
        with self.pool.connection() as conn:
            with conn.transaction():
                self.migrations.run(conn)

    def close(self):
        self.pool.close()

    @contextlib.contextmanager
    def transaction(self) -> Iterator[Any]:
        with self.pool.connection() as connection:
            with connection.transaction():
                yield connection

    @staticmethod
    def object_key(source: IdentityNamespace, object_id: str) -> tuple[str, str, str, str, str]:
        return source.provider, source.tenant, source.connector, source.source_instance, object_id

    def checkpoint(self, connector: str, value: str, complete: bool, *, source: IdentityNamespace | None = None) -> None:
        source = source or IdentityNamespace("unknown", "default", connector=connector)
        with self.transaction() as conn:
            current = conn.execute("SELECT value FROM ingestion_checkpoints WHERE provider=%s AND tenant=%s AND connector=%s AND source_instance=%s", self.object_key(source, "")[:-1]).fetchone()
            if current and str(value) < str(current[0]):
                raise ValueError("checkpoint cannot move backwards")
            conn.execute("""INSERT INTO ingestion_checkpoints
                (provider,tenant,connector,source_instance,value,complete)
                VALUES (%s,%s,%s,%s,%s,%s)
                ON CONFLICT (provider,tenant,connector,source_instance)
                DO UPDATE SET value=EXCLUDED.value, complete=EXCLUDED.complete, updated_at=now()""",
                         (*self.object_key(source, "")[:-1], value, complete))

    def get_checkpoint(self, source: IdentityNamespace) -> tuple[str, bool] | None:
        with self.pool.connection() as conn:
            row = conn.execute("""SELECT value,complete FROM ingestion_checkpoints
                WHERE provider=%s AND tenant=%s AND connector=%s AND source_instance=%s""",
                               (source.provider, source.tenant, source.connector, source.source_instance)).fetchone()
        return (row[0], row[1]) if row else None

    def accept(self, change: CanonicalChange, *, raw_object_uri: str, content_hash: str,
               audit_event: tuple[str, str, str] | None = None) -> RevisionOutcome:
        """Accept raw link, authority state, idempotency, outbox and audit atomically."""
        source = change.source
        key = self.object_key(source, change.object_id)
        object_key = ObjectKey.from_change(change).encoded()
        value = cast(Any, change.value)
        payload = None if value is None else ({
            "document_id": value.document_id, "title": value.title,
            "text": value.text, "source_uri": value.source.source_uri,
            "metadata": dict(value.metadata),
        } if hasattr(value, "document_id") else dict(value))
        with self.transaction() as conn:
            fingerprint = json.dumps({"object_key": object_key, "revision": change.revision,
                                      "operation": change.operation.value, "payload": payload,
                                      "content_hash": content_hash}, sort_keys=True, default=str)
            duplicate = conn.execute("SELECT fingerprint FROM ingestion_idempotency WHERE idempotency_key=%s", (change.idempotency_key,)).fetchone()
            if duplicate:
                return RevisionOutcome.DUPLICATE if duplicate[0] == fingerprint else RevisionOutcome.CONFLICT
            row = conn.execute("""SELECT revision FROM ingestion_authority
                WHERE provider=%s AND tenant=%s AND connector=%s AND source_instance=%s AND object_id=%s
                FOR UPDATE""", key).fetchone()
            current = row[0] if row else 0
            if change.revision <= current:
                return RevisionOutcome.STALE
            if change.revision > current + 1:
                conn.execute("""INSERT INTO ingestion_gaps
                    (object_key,expected_revision,received_revision,idempotency_key,payload)
                    VALUES (%s,%s,%s,%s,%s) ON CONFLICT (idempotency_key) DO NOTHING""",
                             (object_key, current + 1, change.revision, change.idempotency_key,
                              json.dumps(payload)))
                return RevisionOutcome.GAP
            conn.execute("""INSERT INTO ingestion_authority
                (provider,tenant,connector,source_instance,object_id,revision,operation,payload,raw_object_uri,content_hash,observed_at)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                         (*key, change.revision, change.operation.value, json.dumps(payload), raw_object_uri,
                          content_hash, change.occurred_at))
            conn.execute("INSERT INTO ingestion_idempotency(idempotency_key,object_key,revision,fingerprint) VALUES (%s,%s,%s,%s)",
                         (change.idempotency_key, object_key, change.revision, fingerprint))
            conn.execute("INSERT INTO ingestion_outbox(idempotency_key,object_key,tenant,workload,payload) VALUES (%s,%s,%s,%s,%s)",
                         (change.idempotency_key, object_key, source.tenant, source.connector, json.dumps(payload)))
            if audit_event:
                event_id, action, actor = audit_event
                conn.execute("INSERT INTO ingestion_audit(event_id,action,actor,target,tenant) VALUES (%s,%s,%s,%s,%s)",
                             (event_id, action, actor, change.object_id, source.tenant))
        return RevisionOutcome.ACCEPTED

    def claim_outbox(self, worker: str, *, tenant: str, workload: str, limit: int = 100, lease_seconds: int = 60) -> tuple[dict[str, Any], ...]:
        """Claim pending deliveries; lease expiry makes crash recovery safe."""
        with self.transaction() as conn:
            conn.execute("UPDATE ingestion_outbox SET status='pending', lease_owner=NULL, lease_expires_at=NULL WHERE status='claimed' AND lease_expires_at <= now()")
            rows = conn.execute("""WITH picked AS (
                SELECT sequence FROM ingestion_outbox
                WHERE status='pending' AND available_at <= now() AND tenant=%s AND workload=%s
                ORDER BY sequence FOR UPDATE SKIP LOCKED LIMIT %s
            ) UPDATE ingestion_outbox o SET status='claimed', lease_owner=%s, lease_expires_at=now() + (%s * interval '1 second'), attempts=o.attempts+1
              FROM picked WHERE o.sequence=picked.sequence
              RETURNING o.sequence,o.idempotency_key,o.object_key,o.payload,o.attempts""", (tenant, workload, limit, worker, lease_seconds)).fetchall()
        return tuple({"sequence": r[0], "idempotency_key": r[1], "object_key": r[2],
                      "payload": r[3], "attempts": r[4], "worker": worker, "tenant": tenant, "workload": workload} for r in rows)

    def mark_outbox_applied(self, sequence: int, worker: str) -> None:
        with self.transaction() as conn:
            conn.execute("UPDATE ingestion_outbox SET status='applied', lease_owner=NULL, lease_expires_at=NULL WHERE sequence=%s AND status='claimed' AND lease_owner=%s", (sequence, worker))

    def mark_outbox_failed(self, sequence: int, reason: str, *, max_attempts: int = 5) -> None:
        with self.transaction() as conn:
            row = conn.execute("SELECT attempts,lease_owner FROM ingestion_outbox WHERE sequence=%s FOR UPDATE", (sequence,)).fetchone()
            if not row:
                return
            terminal = row[0] >= max_attempts
            conn.execute("UPDATE ingestion_outbox SET status=%s, available_at=now(), lease_owner=NULL, lease_expires_at=NULL WHERE sequence=%s",
                         ("dead" if terminal else "pending", sequence))
            if terminal:
                conn.execute("INSERT INTO ingestion_dead_letters(sequence,reason) VALUES (%s,%s) ON CONFLICT DO NOTHING",
                             (sequence, reason))


class PostgresIngestionService:
    """Small production composition service; retrieval remains out of scope."""

    def __init__(self, repository: PostgresAuthorityRepository, connector: Any, canonicalizer: Any,
                 *, raw_storage=None, identity_provider=None, key_provider=None, telemetry=None):
        self.repository, self.connector, self.canonicalizer = repository, connector, canonicalizer
        self.raw_storage, self.identity_provider, self.key_provider, self.telemetry = raw_storage, identity_provider, key_provider, telemetry

    def _authorize(self, metadata, tenant: str, source_instance: str):
        if self.identity_provider is None:
            return None
        token = metadata.get("oidc_token") if hasattr(metadata, "get") else None
        if not token:
            raise PermissionError("authenticated OIDC token required for production ingestion")
        try:
            principal = self.identity_provider.validate(token)
        except Exception as exc:
            raise PermissionError("invalid production identity") from exc
        if not principal.can_read(tenant, source_instance):
            raise PermissionError("connector principal outside tenant/source scope")
        return principal

    def ingest_change(self, raw, change, job_id: str) -> bool:
        """Persist connector envelope without collapsing revision or operation."""
        self._authorize(raw.metadata, change.source.tenant, change.source.source_instance)
        raw = type(raw)(raw.source, raw.payload, _without_credentials(raw.metadata), raw.schema_version, raw.envelope_id)
        raw_uri = raw.source.source_uri
        if self.raw_storage is not None:
            raw_uri = self.raw_storage.put(
                f"{change.source.tenant}/{change.source.connector}/{change.object_id}/{change.revision}",
                raw.payload, metadata={"tenant": change.source.tenant, "content-hash": raw.source.content_hash})
        outcome = self.repository.accept(change, raw_object_uri=raw_uri,
                                         content_hash=raw.source.content_hash,
                                         audit_event=(change.idempotency_key, change.operation.value, job_id))
        if self.telemetry:
            self.telemetry.counter(f"ingestion.{outcome.value}")
        return outcome in (RevisionOutcome.ACCEPTED, RevisionOutcome.DUPLICATE)

    def ingest(self, item, job_id: str) -> bool:
        from .adapters import source_version
        from .domain import ACL, RawRecord
        from .protocol import CanonicalChange, Operation, PermissionState, ProvenanceLink

        self._authorize(item.metadata, item.tenant, item.source_instance)
        source = source_version(item)
        raw = RawRecord(source, item.payload, _without_credentials(item.metadata))
        acl = item.permissions or ACL(None)  # unresolved identity is fail-closed
        document = self.canonicalizer.canonicalize(raw, acl)
        key_material = "\x00".join((item.provider, item.tenant, item.connector,
                                    item.source_instance, item.external_id, source.version))
        event_id = __import__("hashlib").sha256(key_material.encode()).hexdigest()
        change = CanonicalChange(document.document_id, IdentityNamespace(
            item.provider, item.tenant, connector=item.connector,
            source_instance=item.source_instance), 1, Operation.UPSERT, document,
            event_id, ProvenanceLink("raw", source.source_id), PermissionState(acl))
        outcome = self.repository.accept(change, raw_object_uri=source.source_uri,
                                         content_hash=source.content_hash,
                                         audit_event=(event_id, "ingest", job_id))
        return outcome in (RevisionOutcome.ACCEPTED, RevisionOutcome.DUPLICATE)


_CREDENTIAL_KEYS = {"oidc_token", "bearer", "bearer_token", "access_token", "refresh_token", "id_token", "authorization"}
def _without_credentials(metadata):
    return {key: value for key, value in dict(metadata or {}).items()
            if str(key).lower() not in _CREDENTIAL_KEYS}
