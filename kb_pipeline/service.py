from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from .adapters import source_version
from .domain import ACL, AuditEvent, CanonicalDocument, Input, RawRecord
from .protocol import (CanonicalChange, IdentityNamespace, KnowledgeEngine, Operation,
                       PermissionState, ProvenanceLink, RelationalReferenceLedger,
                       StateProjection, LexicalProjection)
import sqlite3


class KnowledgeService:
    """Functional orchestration; adapters own effects and are injected."""
    def __init__(self, store, index, acl_resolver, canonicalizer, audit, revocation_grace=timedelta(minutes=15), hard_max=timedelta(minutes=30), ledger=None):
        if revocation_grace > hard_max: raise ValueError("revocation grace exceeds hard maximum")
        self.store, self.index, self.acl, self.canonicalizer, self.audit = store, index, acl_resolver, canonicalizer, audit
        self.revocation_grace, self.hard_max = revocation_grace, hard_max
        self.ledger = ledger or RelationalReferenceLedger(getattr(store, "db", sqlite3.connect(":memory:")))
        self._suppressed: dict[str, datetime] = (store.all_revocations() if hasattr(store, "all_revocations") else {})
        self.engine = KnowledgeEngine(self.ledger, store, (StateProjection(), LexicalProjection(index, self._index_visible)))
        self._writer = self.engine._writer
        # Projection is disposable. Rebuild it from canonical durable state on composition.
        for doc in store.all():
            suppressed_until = self._suppressed.get(doc.source.source_id)
            if not doc.tombstoned and doc.acl.readers is not None and (suppressed_until is None or suppressed_until <= datetime.now(timezone.utc)):
                index.replace(doc)

    def _index_visible(self, change):
        until = self._suppressed.get(change.value.source.source_id)
        return until is None or change.value.source.observed_at <= until - self.hard_max + self.revocation_grace

    def ingest(self, item: Input, job_id: str) -> bool:
        event_id = hashlib.sha256((job_id + item.external_id).encode()).hexdigest()
        audit_events = self.audit.all_audit() if hasattr(self.audit, "all_audit") else self.audit.all()
        if any(event.event_id == event_id for event in audit_events): return False
        source = source_version(item)
        record = RawRecord(source, item.payload, item.metadata)
        if hasattr(self.store, "save_raw"): self.store.save_raw(record)
        doc = self.canonicalizer.canonicalize(record, self.acl.resolve(record))
        suppressed_until = self._suppressed.get(doc.source.source_id)
        refresh_within_grace = suppressed_until is not None and self._within_revocation_grace(item.observed_at, suppressed_until)
        source_ns = IdentityNamespace(provider=item.provider, tenant=item.tenant, connector=item.connector, source_instance=item.source_instance)
        prior_revision = self.ledger.revision_for_idempotency(event_id) if hasattr(self.ledger, "revision_for_idempotency") else None
        revision = prior_revision or self.ledger.revision(source_ns, doc.document_id) + 1
        change = CanonicalChange(doc.document_id, source_ns, revision, Operation.DELETE if doc.tombstoned else Operation.UPSERT,
                                 None if doc.tombstoned else doc, event_id, ProvenanceLink("raw", source.source_id), PermissionState(doc.acl))
        # Ledger append and all derived mutations flow through engine/outbox.
        # Raw artifact was durably linked before append, so retries never lose it.
        with self._writer:
            if not self.engine.apply(change):
                pending = any(status in ("pending", "failed") for _, status in self.ledger.outbox())
                if pending:
                    self.engine.process_outbox()
                    self.audit.append(AuditEvent(event_id, "ingest", job_id, doc.document_id))
                    return True
                if any(status == "applied" for _, status in self.ledger.outbox()):
                    self.engine.replay(rebuild=True)
                    self.audit.append(AuditEvent(event_id, "ingest", job_id, doc.document_id))
                    return True
                return False
        if refresh_within_grace:
            if not doc.tombstoned and doc.acl.readers is not None:
                del self._suppressed[doc.source.source_id]
                suppressed_until = None
                self.engine.replay(rebuild=True)
        self.audit.append(AuditEvent(event_id, "ingest", job_id, doc.document_id))
        return True

    def reconcile(self, connector, job_id: str) -> dict:
        """One serialized caller at a time; only complete scans authorize deletion."""
        scan = connector.scan() if hasattr(connector, "scan") else __import__("kb_pipeline.domain", fromlist=["ScanResult"]).ScanResult(tuple(connector.read()), True)
        seen = set()
        for item in scan.records:
            seen.add(item.external_id); self.ingest(item, job_id)
        deleted = 0
        if scan.complete:
            for doc in self.store.all():
                if doc.source.source_id not in seen and doc.source.source_uri.startswith("file:"):
                    self.tombstone(doc.document_id, job_id); deleted += 1
        if hasattr(self.store, "checkpoint"):
            with self._writer: self.store.checkpoint(connector.name, job_id, scan.complete)
        return {"seen": len(seen), "deleted": deleted, "complete": scan.complete, "reason": scan.reason}

    def _within_revocation_grace(self, observed_at: datetime, suppressed_until: datetime) -> bool:
        revoked_at = suppressed_until - self.hard_max
        return observed_at <= revoked_at + self.revocation_grace

    def revoke_source(self, source_id: str, at: datetime | None = None) -> None:
        at = at or datetime.now(timezone.utc)
        # Suppression lasts hard maximum; downstream ACL refresh can restore visibility sooner.
        self._suppressed[source_id] = at + self.hard_max
        if hasattr(self.store, "save_revocation"):
            self.store.save_revocation(source_id, self._suppressed[source_id])
        with self._writer:
            for doc in self.store.all():
                if doc.source.source_id == source_id: self.index.remove(doc.document_id)

    def search(self, query: str, identity: str, is_admin=False):
        result = []
        for hit in self.index.search(query):
            doc = self.store.get(hit.document_id)
            suppressed_until = self._suppressed.get(doc.source.source_id) if doc else None
            suppressed = suppressed_until is not None and suppressed_until > datetime.now(timezone.utc)
            if doc and not doc.tombstoned and doc.acl.permits(identity, is_admin) and not suppressed: result.append(hit)
        return result

    def search_metadata(self, hit):
        doc = self.store.get(hit.document_id)
        source = self._source_for(hit.document_id, doc.source.source_id) if doc else None
        source = source or IdentityNamespace("unknown", "unknown", "unknown")
        digest = hashlib.sha256(source.source_instance.encode()).hexdigest()[:16] if source.source_instance else "unknown"
        locator = self._safe_locator(doc.source.source_id if doc else "")
        reference = f"raw:{locator}" if locator != "unknown" else "unknown"
        key = json.dumps({"provider": source.provider, "tenant": source.tenant, "connector": source.connector,
                          "source_instance": digest, "object": hit.document_id}, separators=(",", ":"), sort_keys=True)
        sequence = self._ledger_sequence(hit.document_id, source)
        return {"source_identity": f"{source.provider}:{source.tenant}:{source.connector}:{digest}",
                "source_locator": locator, "object_key": key, "source_version": hit.source_version,
                "raw_record_reference": reference, "provenance_reference": reference,
                "observed_at": doc.source.observed_at.isoformat() if doc else "unknown", "indexed_at": "unknown",
                "ledger_sequence": sequence, "projection_sequence": sequence, "status": "complete",
                "freshness_status": "unknown", "provenance": ([{"kind": "raw", "identifier": locator}] if locator != "unknown" else []),
                "evidence": [{"type": "indexed_document", "status": "supported"}]}

    @staticmethod
    def _safe_locator(value):
        value = value.strip() if isinstance(value, str) else ""
        if not value or value.startswith(("/", "\\")) or "://" in value or len(value) > 256:
            return "unknown"
        return value

    def _source_for(self, document_id, source_id):
        for change in reversed(tuple(self.ledger.changes())):
            if change.object_id == document_id and change.value is not None:
                return change.source
        return None

    def _ledger_sequence(self, document_id, source):
        row = self.ledger.db.execute(
            "SELECT max(sequence) FROM protocol_ledger WHERE object_id=? AND source=?",
            (document_id, json.dumps((source.provider, source.tenant, source.subject,
                                      source.connector, source.source_instance), separators=(",", ":"))),
        ).fetchone()
        return row[0] if row and row[0] is not None else None

    def tombstone(self, document_id: str, actor: str) -> None:
        doc = self.store.get(document_id)
        if doc is not None:
            source = IdentityNamespace("local", "default", "service", source_instance="")
            revision = self.ledger.revision(source, document_id) + 1
            change = CanonicalChange(document_id, source, revision, Operation.DELETE, None,
                                                 hashlib.sha256(("tombstone:" + document_id + actor).encode()).hexdigest(),
                                                 ProvenanceLink("service", actor), PermissionState(doc.acl))
            with self._writer: self.engine.apply(change)
        self.audit.append(AuditEvent(hashlib.sha256(("tombstone:" + document_id + actor).encode()).hexdigest(), "tombstone", actor, document_id))

    def purge(self, before: datetime, actor: str = "system", *, source_id: str | None = None, document_id: str | None = None) -> dict:
        """Reference purge removes durable raw/current/search state.

        External projections remain adapter-owned; unavailable adapters are not
        represented as successfully purged.
        """
        candidates = tuple(doc.document_id for doc in self.store.all()
                           if doc.tombstoned and doc.deleted_at and doc.deleted_at < before
                           and (source_id is None or doc.source.source_id == source_id)
                           and (document_id is None or doc.document_id == document_id))
        scope = "document" if document_id else "source" if source_id else "tombstoned-before"
        purge_id = self.store.begin_purge(scope, document_id or source_id or before.isoformat(), len(candidates)) if hasattr(self.store, "begin_purge") else None
        try:
            kwargs = {"purge_id": purge_id, "source_id": source_id, "document_id": document_id}
            count = self.store.purge(before, **kwargs) if purge_id else self.store.purge(before, source_id=source_id, document_id=document_id)
        except Exception as exc:
            if purge_id: self.store.finish_purge(purge_id, 0, "failed", type(exc).__name__)
            raise
        for document_id in candidates:
            self.index.remove(document_id)
        self.audit.append(AuditEvent(
            hashlib.sha256(("purge:" + before.isoformat() + actor).encode()).hexdigest(),
            "purge", actor, f"before:{before.isoformat()}"
        ))
        return {"purge_id": purge_id, "purged": count, "reference_path": "complete", "external_projections": "not_claimed"}

    def health(self):
        ledger = self.ledger
        outbox = ledger.outbox() if hasattr(ledger, "outbox") else ()
        checkpoints = {name: ledger.checkpoint(name) for name in ("default:state", "default:document", "default:lexical") if hasattr(ledger, "checkpoint")}
        latest = len(tuple(ledger.changes())) if hasattr(ledger, "changes") else 0
        return {"ledger_sequence": latest, "outbox_pending": sum(status in ("pending", "claimed", "failed") for _, status in outbox), "outbox_failed": sum(status == "failed" for _, status in outbox), "dead_letters": len(ledger.dead_letters()) if hasattr(ledger, "dead_letters") else 0, "gaps": len(ledger.gaps()) if hasattr(ledger, "gaps") else 0, "checkpoints": checkpoints, "projection_lag": {k: max(0, latest-v) for k,v in checkpoints.items()}}

    def readiness(self):
        try:
            self.store.status(); health = self.health()
            ready = health["gaps"] == 0 and health["dead_letters"] == 0
            return {"status": "ready" if ready else "not_ready", "checks": {"storage": True, "replay": ready}, "health": health}
        except Exception as exc:
            return {"status": "not_ready", "checks": {"storage": False}, "error": type(exc).__name__}
