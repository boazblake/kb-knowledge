"""PostgreSQL authority adapter.

Psycopg owns pooling, parameter binding, and transaction boundaries. This module
contains no workflow engine or provider SDK implementation.
"""
from __future__ import annotations

import contextlib
import hashlib
import json
import re
import random
from urllib.parse import urlsplit
from pathlib import Path
from typing import Any, Iterator, cast

from .protocol import CanonicalChange, IdentityNamespace, ObjectKey, RevisionOutcome
from .phase4_core import ReplayEnvelope, EnvelopeOperation, resolve_legacy_identity
from .telemetry import span as telemetry_span


class PostgresUnavailable(RuntimeError):
    """Required PostgreSQL driver or database is unavailable."""


def _normalize_fingerprint(value: object) -> str | None:
    """Normalize PostgreSQL/application fingerprint values without coercion."""
    if isinstance(value, str):
        return value
    if isinstance(value, (bytes, bytearray, memoryview)):
        try:
            return bytes(value).decode("utf-8")
        except UnicodeDecodeError:
            return None
    return None


def _fingerprints_match(stored: object, expected: object) -> bool:
    stored_text = _normalize_fingerprint(stored)
    expected_text = _normalize_fingerprint(expected)
    return stored_text is not None and expected_text is not None and stored_text == expected_text


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

    def checkpoint(self, connector: str, value: str, complete: bool, *, source: IdentityNamespace | None = None, cursor_semantics=None) -> None:
        source = source or IdentityNamespace("unknown", "default", connector=connector)
        with self.transaction() as conn:
            current = conn.execute("SELECT value FROM ingestion_checkpoints WHERE provider=%s AND tenant=%s AND connector=%s AND source_instance=%s", self.object_key(source, "")[:-1]).fetchone()
            if current and cursor_semantics is None:
                raise ValueError("connector cursor comparator required")
            if current and cursor_semantics.compare(value, current[0]) < 0:
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
        with self.transaction() as conn:
            return self._accept(conn, change, raw_object_uri=raw_object_uri,
                                content_hash=content_hash, audit_event=audit_event)

    def accept_with_sequence(self, change: CanonicalChange, *, raw_object_uri: str,
                             content_hash: str, correlation_id: str | None = None):
        with self.transaction() as conn:
            outcome = self._accept(conn, change, raw_object_uri=raw_object_uri,
                                   content_hash=content_hash,
                                   audit_event=(correlation_id or change.idempotency_key,
                                                change.operation.value, "pipeline"))
            row = conn.execute("SELECT sequence FROM ingestion_outbox WHERE idempotency_key=%s",
                               (change.idempotency_key,)).fetchone()
            return outcome, (int(row[0]) if row else 0)

    def accept_and_checkpoint(self, change: CanonicalChange, *, raw_object_uri: str,
                              content_hash: str, checkpoint: tuple[IdentityNamespace, str, bool] | None = None,
                              audit_event: tuple[str, str, str] | None = None, cursor_semantics=None) -> RevisionOutcome:
        """Commit change and cursor together; caller advances in-memory cursor after return."""
        with self.transaction() as conn:
            outcome = self._accept(conn, change, raw_object_uri=raw_object_uri,
                                   content_hash=content_hash, audit_event=audit_event)
            if checkpoint and outcome in (RevisionOutcome.ACCEPTED, RevisionOutcome.DUPLICATE):
                source, value, complete = checkpoint
                current = conn.execute("""SELECT value FROM ingestion_checkpoints
                    WHERE provider=%s AND tenant=%s AND connector=%s AND source_instance=%s
                    FOR UPDATE""", (source.provider, source.tenant, source.connector, source.source_instance)).fetchone()
                if current and cursor_semantics is None:
                    raise ValueError("connector cursor comparator required")
                if current and cursor_semantics.compare(value, current[0]) < 0:
                    raise ValueError("checkpoint cannot move backwards")
                conn.execute("""INSERT INTO ingestion_checkpoints
                    (provider,tenant,connector,source_instance,value,complete)
                    VALUES (%s,%s,%s,%s,%s,%s)
                    ON CONFLICT (provider,tenant,connector,source_instance)
                    DO UPDATE SET value=EXCLUDED.value, complete=EXCLUDED.complete, updated_at=now()""",
                    (source.provider, source.tenant, source.connector, source.source_instance,
                     value, complete))
            return outcome

    def accept_batch(self, entries, *, checkpoint=None, cursor_semantics=None):
        """One PostgreSQL transaction for complete batch authority effects."""
        with self.transaction() as conn:
            outcomes = []
            for change, uri, content_hash, audit in entries:
                outcomes.append(self._accept(conn, change, raw_object_uri=uri,
                                             content_hash=content_hash, audit_event=audit))
                conn.execute("UPDATE ingestion_raw_objects SET status='committed', committed_at=now() WHERE uri=%s", (uri,))
            outcomes = tuple(outcomes)
            if checkpoint is not None:
                source, value, complete = checkpoint
                current = conn.execute("""SELECT value FROM ingestion_checkpoints
                    WHERE provider=%s AND tenant=%s AND connector=%s AND source_instance=%s FOR UPDATE""",
                    (source.provider, source.tenant, source.connector, source.source_instance)).fetchone()
                if current and (cursor_semantics is None or cursor_semantics.compare(value, current[0]) < 0):
                    raise ValueError("checkpoint comparator rejected cursor")
                conn.execute("""INSERT INTO ingestion_checkpoints
                    (provider,tenant,connector,source_instance,value,complete) VALUES (%s,%s,%s,%s,%s,%s)
                    ON CONFLICT (provider,tenant,connector,source_instance) DO UPDATE
                    SET value=EXCLUDED.value, complete=EXCLUDED.complete, updated_at=now()""",
                    (source.provider, source.tenant, source.connector, source.source_instance, value, complete))
            return outcomes

    def stage_raw(self, source, object_id, revision, uri, content_hash):
        with self.transaction() as conn:
            conn.execute("""INSERT INTO ingestion_raw_objects
                (uri,provider,tenant,connector,source_instance,object_id,revision,content_hash)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (uri) DO UPDATE SET status='staged', last_error=NULL""",
                (uri, source.provider, source.tenant, source.connector, source.source_instance,
                 object_id, str(revision), content_hash))

    def register_orphan(self, source, object_id, revision, uri, content_hash, reason):
        """Persist S3-success/authority-failure for tenant-safe bounded sweeper."""
        with self.transaction() as conn:
            conn.execute("""INSERT INTO ingestion_raw_objects
                (uri,provider,tenant,connector,source_instance,object_id,revision,content_hash,status,orphaned_at,last_error)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,'orphaned',now(),%s)
                ON CONFLICT (uri) DO UPDATE SET status='orphaned', orphaned_at=now(), last_error=EXCLUDED.last_error""",
                (uri, source.provider, source.tenant, source.connector, source.source_instance,
                 object_id, str(revision), content_hash, reason[:1000]))

    def queue_metrics(self, *, tenant: str, workload: str):
        with self.pool.connection() as conn:
            row = conn.execute("""SELECT count(*), COALESCE(EXTRACT(epoch FROM (now()-min(created_at))),0)
                FROM ingestion_outbox WHERE tenant=%s AND workload=%s AND status='pending'""",
                (tenant, workload)).fetchone()
        return {"queue_depth": int(row[0]), "queue_age_seconds": float(row[1])}

    def reap_orphans(self, *, tenant: str, older_than_seconds: int = 3600, limit: int = 100):
        with self.transaction() as conn:
            return tuple(conn.execute("""SELECT uri,provider,connector,source_instance,object_id,revision
                FROM ingestion_raw_objects WHERE tenant=%s AND status='orphaned'
                AND orphaned_at < now()-(%s*interval '1 second') ORDER BY orphaned_at LIMIT %s""",
                (tenant, older_than_seconds, limit)).fetchall())

    def mark_orphan_reaped(self, uri):
        with self.transaction() as conn:
            conn.execute("UPDATE ingestion_raw_objects SET status='reaped' WHERE uri=%s AND status='orphaned'", (uri,))

    def _accept(self, conn, change: CanonicalChange, *, raw_object_uri: str,
                content_hash: str, audit_event: tuple[str, str, str] | None = None) -> RevisionOutcome:
        source = change.source
        object_key = ObjectKey.from_change(change).encoded()
        key = (*self.object_key(source, change.object_id), object_key)
        if conn.execute("SELECT 1 FROM purge_tombstones WHERE object_key=%s", (ObjectKey.from_change(change).encoded(),)).fetchone():
            raise ValueError("purged object cannot be resurrected")
        value = cast(Any, change.value)
        payload = None if value is None else ({
            "document_id": value.document_id, "title": value.title,
            "text": value.text, "source_uri": value.source.source_uri,
            "metadata": dict(value.metadata),
        } if hasattr(value, "document_id") else dict(value))
        fingerprint = json.dumps({"object_key": object_key, "revision": change.revision,
                                      "operation": change.operation.value, "payload": payload,
                                      "content_hash": content_hash}, sort_keys=True, default=str)
        duplicate = conn.execute("SELECT fingerprint FROM ingestion_idempotency WHERE idempotency_key=%s", (change.idempotency_key,)).fetchone()
        if duplicate:
            return RevisionOutcome.DUPLICATE if _fingerprints_match(duplicate[0], fingerprint) else RevisionOutcome.CONFLICT
        row = conn.execute("""SELECT revision,operation FROM ingestion_authority
                WHERE provider=%s AND tenant=%s AND connector=%s AND source_instance=%s AND object_id=%s
                FOR UPDATE""", key[:-1]).fetchone()
        current = row[0] if row else 0
        if row and row[1] == "delete" and change.operation.value != "delete":
            return RevisionOutcome.STALE
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
                (provider,tenant,connector,source_instance,object_id,object_key,revision,operation,payload,raw_object_uri,content_hash,observed_at)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (provider,tenant,connector,source_instance,object_id)
                DO UPDATE SET revision=EXCLUDED.revision, operation=EXCLUDED.operation,
                  payload=EXCLUDED.payload, raw_object_uri=EXCLUDED.raw_object_uri,
                  content_hash=EXCLUDED.content_hash, observed_at=EXCLUDED.observed_at,
                  updated_at=now()""",
                  (*key, change.revision, change.operation.value, json.dumps(payload), raw_object_uri,
                   content_hash, change.occurred_at))
        conn.execute("INSERT INTO ingestion_idempotency(idempotency_key,object_key,revision,fingerprint) VALUES (%s,%s,%s,%s)",
                          (change.idempotency_key, object_key, change.revision, fingerprint))
        semantic = resolve_legacy_identity(tenant=source.tenant, object_id=change.object_id,
                                           source=source.connector, provider=source.provider,
                                           connector=source.connector, source_instance=source.source_instance)
        envelope = ReplayEnvelope(
            event_id=hashlib.sha256(f"{source.tenant}:{change.idempotency_key}".encode()).hexdigest(),
            idempotency_key=change.idempotency_key, semantic_key=semantic, revision=change.revision,
            operation=EnvelopeOperation(change.operation.value), payload=payload,
            raw_reference={"uri": raw_object_uri, "content_hash": content_hash},
            provenance={"provider": source.provider, "connector": source.connector,
                        "source_instance": source.source_instance, "subject": source.subject},
            permissions={"readers": None if change.permissions.acl.readers is None else list(change.permissions.acl.readers),
                         "admins": list(change.permissions.acl.admins), "resolved": change.permissions.resolved},
            correlation_id=audit_event[0] if audit_event else change.idempotency_key,
            observed_at=change.occurred_at)
        conn.execute("""INSERT INTO ingestion_outbox
            (idempotency_key,object_key,tenant,workload,payload,envelope,event_id,correlation_id)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s)""",
                          (change.idempotency_key, object_key, source.tenant, source.connector,
                           json.dumps(payload), envelope.serialize(), envelope.event_id, envelope.correlation_id))
        if audit_event:
            event_id, action, actor = audit_event
            conn.execute("INSERT INTO ingestion_audit(event_id,action,actor,target,tenant) VALUES (%s,%s,%s,%s,%s)",
                             (event_id, action, actor, change.object_id, source.tenant))
        return RevisionOutcome.ACCEPTED

    def raw_reference(self, source: IdentityNamespace, object_id: str):
        """Return authoritative raw URI/hash/revision, scoped by full object namespace."""
        with self.pool.connection() as conn:
            return conn.execute("""SELECT raw_object_uri,content_hash,revision,operation
                FROM ingestion_authority WHERE provider=%s AND tenant=%s AND connector=%s
                AND source_instance=%s AND object_id=%s""", self.object_key(source, object_id)).fetchone()

    def claim_outbox(self, worker: str, *, tenant: str, workload: str, limit: int = 100, lease_seconds: int = 60) -> tuple[dict[str, Any], ...]:
        """Claim pending deliveries; lease expiry makes crash recovery safe."""
        with self.transaction() as conn:
            conn.execute("""UPDATE ingestion_outbox SET status='pending', lease_owner=NULL,
                lease_expires_at=NULL WHERE status='claimed' AND lease_expires_at <= now()
                AND tenant=%s AND workload=%s""", (tenant, workload))
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
            count = conn.execute("UPDATE ingestion_outbox SET status='applied', completed_by=%s, lease_owner=NULL, lease_expires_at=NULL WHERE sequence=%s AND status='claimed' AND lease_owner=%s", (worker, sequence, worker)).rowcount
            if count != 1:
                raise PermissionError("outbox lease not owned by worker")

    def mark_outbox_failed(self, sequence: int, reason: str, worker: str | None = None, *, max_attempts: int = 5, base_delay_seconds: int = 5, jitter_seconds: int = 3) -> None:
        with self.transaction() as conn:
            row = conn.execute("SELECT attempts,lease_owner FROM ingestion_outbox WHERE sequence=%s FOR UPDATE", (sequence,)).fetchone()
            if not row:
                return
            if not worker or row[1] != worker:
                raise PermissionError("outbox lease not owned by worker")
            terminal = row[0] >= max_attempts
            jitter = random.randint(0, max(0, jitter_seconds))
            delay = base_delay_seconds * (2 ** max(0, row[0] - 1)) + jitter
            conn.execute("""UPDATE ingestion_outbox SET status=%s,
                available_at=now()+(%s*interval '1 second'), retry_at=now()+(%s*interval '1 second'),
                last_error=%s, last_retry_delay_seconds=%s, last_retry_jitter_seconds=%s,
                lease_owner=NULL, lease_expires_at=NULL WHERE sequence=%s""",
                         ("dead" if terminal else "pending", delay, delay, reason[:1000], delay, jitter, sequence))
            if terminal:
                conn.execute("INSERT INTO ingestion_dead_letters(sequence,reason) VALUES (%s,%s) ON CONFLICT DO NOTHING",
                             (sequence, reason))

    def retry_dead_letter(self, sequence: int, *, operator: str) -> None:
        """Explicitly requeue one DLQ item; automatic replay remains disabled."""
        if not operator.strip():
            raise ValueError("operator identity required")
        with self.transaction() as conn:
            count = conn.execute("""UPDATE ingestion_outbox
                SET status='pending', attempts=0, available_at=now(), retry_at=NULL,
                    last_error=NULL, last_retry_delay_seconds=NULL,
                    last_retry_jitter_seconds=NULL, lease_owner=NULL,
                    lease_expires_at=NULL
                WHERE sequence=%s AND status='dead'""", (sequence,)).rowcount
            if count != 1:
                raise ValueError("dead-letter item is not replayable")
            conn.execute("""INSERT INTO ingestion_audit(event_id,action,actor,target,tenant)
                SELECT 'dlq-replay:' || %s, 'dlq-replay', %s, idempotency_key, tenant
                FROM ingestion_outbox WHERE sequence=%s
                ON CONFLICT (event_id) DO NOTHING""", (sequence, operator, sequence))

    # Purge lane: intent/receipts are PostgreSQL durable state, while provider
    # deletion remains owned by injected S3/cache/projection adapters.
    def create_purge_intent(self, intent):
        from .purge import PurgeStatus
        with self.transaction() as conn:
            row = conn.execute("SELECT * FROM purge_intents WHERE idempotency_key=%s", (intent.idempotency_key,)).fetchone()
            if row:
                if row[2] != intent.target or row[4] != intent.correlation_id:
                    raise ValueError("purge idempotency conflict")
                return intent.__class__(row[0], row[1], row[2], row[3], row[4],
                                        intent.decision.__class__(row[5], row[6], row[7], "recovered"))
            conn.execute("""INSERT INTO purge_intents
                (purge_id,idempotency_key,target,actor,correlation_id,data_class,retain_until,legal_hold,status)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                         (intent.purge_id, intent.idempotency_key, intent.target, intent.actor,
                          intent.correlation_id, intent.decision.data_class, intent.decision.retain_until,
                          intent.decision.legal_hold, PurgeStatus.PENDING.value))
        return intent

    def tombstone_for_purge(self, purge_id, target, actor, correlation_id):
        """Commit authority tombstones in transaction before provider hooks execute."""
        with self.transaction() as conn:
            # Target must be canonical full namespace key; bare object IDs are ambiguous.
            rows = conn.execute("""SELECT object_key FROM ingestion_authority
                WHERE object_key=%s FOR UPDATE""", (target,)).fetchall()
            ids = tuple(row[0] for row in rows)
            for object_key in ids:
                conn.execute("""INSERT INTO purge_tombstones
                    (purge_id,object_key,actor,correlation_id) VALUES (%s,%s,%s,%s)
                    ON CONFLICT (object_key) DO NOTHING""", (purge_id, object_key, actor, correlation_id))
            conn.execute("UPDATE purge_intents SET status='running' WHERE purge_id=%s", (purge_id,))
        return ids

    def save_purge_receipt(self, receipt):
        with self.transaction() as conn:
            conn.execute("""INSERT INTO purge_receipts
                (purge_id,store,status,detail,correlation_id) VALUES (%s,%s,%s,%s,%s)
                ON CONFLICT (purge_id,store) DO UPDATE SET status=EXCLUDED.status,
                detail=EXCLUDED.detail, correlation_id=EXCLUDED.correlation_id,
                recorded_at=now()""", (receipt.purge_id, receipt.store, receipt.status.value,
                                        receipt.detail, receipt.correlation_id))

    def purge_receipts(self, purge_id):
        from .purge import ReceiptStatus, StoreReceipt
        with self.pool.connection() as conn:
            rows = conn.execute("SELECT purge_id,store,status,detail,correlation_id FROM purge_receipts WHERE purge_id=%s", (purge_id,)).fetchall()
        return tuple(StoreReceipt(r[0], r[1], ReceiptStatus(r[2]), r[3], r[4]) for r in rows)

    def audit_purge(self, intent, action):
        with self.transaction() as conn:
            conn.execute("""INSERT INTO ingestion_audit(event_id,action,actor,target,tenant)
                VALUES (%s,%s,%s,%s,%s) ON CONFLICT (event_id) DO NOTHING""",
                         (f"{intent.purge_id}:{action}", action, intent.actor, intent.target, "purge"))

    def set_purge_status(self, purge_id, status):
        with self.transaction() as conn:
            conn.execute("UPDATE purge_intents SET status=%s WHERE purge_id=%s", (status.value, purge_id))


class PostgresIngestionService:
    """Small production composition service; retrieval remains out of scope."""

    def __init__(self, repository: PostgresAuthorityRepository, connector: Any, canonicalizer: Any,
                 *, raw_storage=None, identity_provider=None, key_provider=None, telemetry=None):
        self.repository, self.connector, self.canonicalizer = repository, connector, canonicalizer
        self.raw_storage, self.identity_provider, self.key_provider, self.telemetry = raw_storage, identity_provider, key_provider, telemetry

    def _authorize(self, metadata, tenant: str, source_instance: str):
        span = self.telemetry.span("auth.ingestion", component="auth", tenant=tenant) if self.telemetry else contextlib.nullcontext()
        with span:
            return self._authorize_inner(metadata, tenant, source_instance)

    def _authorize_inner(self, metadata, tenant: str, source_instance: str):
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
            from .production_adapters import ArtifactContext
            artifact_context = ArtifactContext(change.source.provider, change.source.tenant,
                                               change.source.connector, change.source.source_instance,
                                               change.object_id, str(change.revision))
            with telemetry_span(self.telemetry, "storage.s3.put", component="s3", tenant=change.source.tenant):
                raw_uri = self.raw_storage.put(
                    artifact_context.key(getattr(self.raw_storage, "prefix", "raw/")), raw.payload,
                    metadata={"tenant": change.source.tenant}, context=artifact_context)
        with telemetry_span(self.telemetry, "authority.postgresql.accept", component="postgresql",
                            tenant=change.source.tenant, workload=change.source.connector):
            outcome = self.repository.accept(change, raw_object_uri=raw_uri,
                                             content_hash=raw.source.content_hash,
                                             audit_event=(change.idempotency_key, change.operation.value, job_id))
        if self.telemetry:
            self.telemetry.counter(f"ingestion.{outcome.value}")
        return outcome in (RevisionOutcome.ACCEPTED, RevisionOutcome.DUPLICATE)

    def ingest_batch(self, batch, job_id: str) -> bool:
        """Stage every raw object, then commit whole batch and checkpoint in one SQL transaction."""
        entries, staged = [], []
        try:
            for raw, change in batch.envelopes:
                self._authorize(raw.metadata, change.source.tenant, change.source.source_instance)
                uri = raw.source.source_uri
                if self.raw_storage is not None:
                    from .production_adapters import ArtifactContext
                    context = ArtifactContext(change.source.provider, change.source.tenant, change.source.connector,
                                              change.source.source_instance, change.object_id, str(change.revision))
                    uri = self.raw_storage.put(context.key(self.raw_storage.prefix), raw.payload,
                                               metadata={"tenant": change.source.tenant}, context=context)
                staged.append((change, uri, raw.source.content_hash))
                self.repository.stage_raw(change.source, change.object_id, change.revision, uri, raw.source.content_hash)
                entries.append((change, uri, raw.source.content_hash,
                                (change.idempotency_key, change.operation.value, job_id)))
            checkpoint = None
            if batch.complete and batch.cursor is not None:
                source = batch.envelopes[-1][1].source if batch.envelopes else self.connector.source
                checkpoint = (source, batch.cursor, True)
            outcomes = self.repository.accept_batch(entries, checkpoint=checkpoint,
                                                    cursor_semantics=getattr(batch, "cursor_semantics", None))
            if self.telemetry:
                self.telemetry.counter("ingestion.batch.accepted", len(outcomes))
            return all(outcome in (RevisionOutcome.ACCEPTED, RevisionOutcome.DUPLICATE) for outcome in outcomes)
        except Exception as exc:
            # DB failure after S3 success is durable orphan state; KMS/S3 failure has no object to register.
            for change, uri, content_hash in staged:
                try:
                    self.repository.register_orphan(change.source, change.object_id, change.revision,
                                                    uri, content_hash, type(exc).__name__ + ": " + str(exc))
                except Exception:
                    if self.telemetry: self.telemetry.counter("ingestion.orphan_registry.failure")
            if self.telemetry: self.telemetry.counter("ingestion.batch.failed")
            raise

    def read_raw(self, source, object_id: str, *, principal=None) -> bytes:
        """Read only authority-referenced ciphertext and verify plaintext hash."""
        if principal is not None and not principal.can_read(source.tenant, source.connector):
            raise PermissionError("principal outside raw object tenant/source scope")
        if self.raw_storage is None:
            raise ValueError("encrypted raw storage required")
        reference = self.repository.raw_reference(source, object_id)
        if not reference:
            raise LookupError("authoritative raw object unavailable")
        uri, content_hash, revision, _operation = reference
        if isinstance(uri, (bytes, bytearray, memoryview)):
            uri = bytes(uri).decode("utf-8")
        if isinstance(content_hash, (bytes, bytearray, memoryview)):
            content_hash = bytes(content_hash).decode("utf-8")
        parsed = urlsplit(uri)
        if parsed.scheme != "s3" or parsed.netloc != getattr(self.raw_storage, "bucket", parsed.netloc):
            raise ValueError("raw object store mismatch")
        from .production_adapters import ArtifactContext
        context = ArtifactContext(source.provider, source.tenant, source.connector,
                                  source.source_instance, object_id, str(revision))
        key = context.key(self.raw_storage.prefix)
        if parsed.path.lstrip("/") != key:
            raise ValueError("raw object reference/context mismatch")
        payload = self.raw_storage.get(key, context=context)
        if hashlib.sha256(payload).hexdigest() != content_hash:
            raise ValueError("authoritative raw content hash mismatch")
        return payload

    def sweep_orphans(self, *, tenant: str, limit: int = 100, older_than_seconds: int = 3600) -> int:
        """Delete only bounded, tenant-scoped orphan objects, then mark registry rows."""
        if self.raw_storage is None:
            raise ValueError("encrypted raw storage required")
        rows = self.repository.reap_orphans(tenant=tenant, older_than_seconds=older_than_seconds, limit=limit)
        deleted = 0
        for uri, provider, connector, source_instance, object_id, revision in rows:
            from .production_adapters import ArtifactContext
            context = ArtifactContext(provider, tenant, connector, source_instance, object_id, str(revision))
            self.raw_storage.delete(context.key(self.raw_storage.prefix))
            self.repository.mark_orphan_reaped(uri)
            deleted += 1
        if self.telemetry:
            self.telemetry.counter("ingestion.orphan.swept", deleted, tenant=tenant)
        return deleted

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
        raw_uri = source.source_uri
        if self.raw_storage is not None:
            from .production_adapters import ArtifactContext
            artifact_context = ArtifactContext(item.provider, item.tenant, item.connector,
                                               item.source_instance, item.external_id, str(change.revision))
            raw_uri = self.raw_storage.put(artifact_context.key(getattr(self.raw_storage, "prefix", "raw/")), item.payload,
                                           metadata={"tenant": item.tenant}, context=artifact_context)
        outcome = self.repository.accept(change, raw_object_uri=raw_uri,
                                         content_hash=source.content_hash,
                                         audit_event=(event_id, "ingest", job_id))
        return outcome in (RevisionOutcome.ACCEPTED, RevisionOutcome.DUPLICATE)


_CREDENTIAL_KEYS = {"oidc_token", "bearer", "bearer_token", "access_token", "refresh_token", "id_token", "authorization"}
def _without_credentials(metadata):
    return {key: value for key, value in dict(metadata or {}).items()
            if str(key).lower() not in _CREDENTIAL_KEYS}
