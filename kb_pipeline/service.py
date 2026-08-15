from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from .adapters import is_jpeg, source_version
from .domain import ACL, AuditEvent, CanonicalDocument, Input, RawRecord, SearchHit
from .protocol import (CanonicalChange, IdentityNamespace, KnowledgeEngine, Operation,
                       PermissionState, ProvenanceLink, RelationalReferenceLedger,
                       StateProjection, LexicalProjection)
import sqlite3
from .answer import AnswerUnavailable, AnswerValidationError, DeterministicAnswerer, citation_dtos, validate_answer_result
from .vision import VISION_PROMPT_VERSION, VISION_SCHEMA_VERSION, LABEL_FIELDS, validate_observation
from .embedding import input_hash, unpack_vector


class KnowledgeService:
    """Functional orchestration; adapters own effects and are injected."""
    def __init__(self, store, index, acl_resolver, canonicalizer, audit, revocation_grace=timedelta(minutes=15), hard_max=timedelta(minutes=30), ledger=None, max_projection_lag=0, answerer=None, vision_observer=None, semantic_embedder=None):
        if revocation_grace > hard_max: raise ValueError("revocation grace exceeds hard maximum")
        self.store, self.index, self.acl, self.canonicalizer, self.audit = store, index, acl_resolver, canonicalizer, audit
        self.revocation_grace, self.hard_max = revocation_grace, hard_max
        if max_projection_lag < 0: raise ValueError("max_projection_lag must be non-negative")
        self.max_projection_lag = max_projection_lag
        self.answerer = answerer or DeterministicAnswerer()
        self.vision_observer = vision_observer
        self.semantic_embedder = semantic_embedder
        self.semantic_model = getattr(semantic_embedder, "model", None)
        self.ledger = ledger or RelationalReferenceLedger(getattr(store, "db", sqlite3.connect(":memory:")))
        if hasattr(store, "writer_lock") and hasattr(self.ledger, "_lock"):
            self.ledger._lock = self.ledger.writer_lock = store.writer_lock
        self.ledger.db.execute(
            "CREATE INDEX IF NOT EXISTS protocol_ledger_object_sequence_idx "
            "ON protocol_ledger(object_id, sequence DESC)"
        )
        self.ledger.db.commit()
        self._suppressed: dict[str, datetime] = (store.all_revocations() if hasattr(store, "all_revocations") else {})
        self.engine = KnowledgeEngine(self.ledger, store, (StateProjection(), LexicalProjection(index, self._index_visible)))
        self._writer = self.engine._writer
        # Projection/state are disposable. Replay durable ledger without source scans or
        # provider calls, then restore post-ledger validated visual text updates.
        durable_docs = store.all()
        durable_embeddings = store.embedding_rows() if hasattr(store, "embedding_rows") else ()
        extracted_docs = {doc.document_id: doc for doc in durable_docs
                          if doc.metadata.get("image_extraction", {}).get("status") == "success"}
        self.engine.process_outbox(worker="startup", failure=None)
        self.engine.replay(rebuild=True)
        for doc in extracted_docs.values():
            store.put(doc, allow_older=True)
        for row in durable_embeddings:
            doc = store.get(row["document_id"])
            if doc is not None:
                try:
                    store.save_embedding(doc, row["model"], unpack_vector(row["vector"], row["dimensions"]), row["input_hash"])
                except Exception:
                    pass
        for doc in store.all():
            suppressed_until = self._suppressed.get(doc.source.source_id)
            if not doc.tombstoned and doc.acl.readers is not None and (suppressed_until is None or suppressed_until <= datetime.now(timezone.utc)):
                if doc.document_id in extracted_docs:
                    change = next((item for item in reversed(tuple(self.ledger.changes()))
                                   if item.object_id == doc.document_id and item.value is not None), None)
                    index.replace(doc, change.source if change is not None else "default")

    def _index_visible(self, change):
        until = self._suppressed.get(change.value.source.source_id)
        return until is None or change.value.source.observed_at <= until - self.hard_max + self.revocation_grace

    def _run_vision(self, item, doc):
        if not is_jpeg(item.payload) or not hasattr(self.store, "save_image_extraction"):
            return
        model = getattr(self.vision_observer, "model", None)
        if self.vision_observer is None:
            self.store.save_image_extraction(doc.document_id, doc.source.source_id, doc.source.version,
                                             doc.source.content_hash, None, VISION_SCHEMA_VERSION,
                                             VISION_PROMPT_VERSION, "not_requested")
            return
        try:
            observation = self.vision_observer.observe(item.payload, item.external_id)
            status, error = "success", None
        except Exception as exc:
            observation, status, error = None, "failed", type(exc).__name__
        published = self.store.save_image_extraction(doc.document_id, doc.source.source_id, doc.source.version,
                                                     doc.source.content_hash, model, VISION_SCHEMA_VERSION,
                                                     VISION_PROMPT_VERSION, status, observation, error)
        if published:
            refreshed = self.store.get(doc.document_id)
            if refreshed is not None: self.index.replace(refreshed)

    def reextract_images(self, observer, full=False):
        """Explicit maintenance operation; never called by normal startup/index."""
        previous = self.vision_observer
        self.vision_observer = observer
        processed = skipped = 0
        try:
            for doc in self.store.all():
                if doc.tombstoned or doc.metadata.get("mime_type") != "image/jpeg": continue
                extraction = self.store.image_extraction(doc.source.source_id, doc.source.version) if hasattr(self.store, "image_extraction") else None
                if not full and extraction and extraction.get("status") == "success" and extraction.get("model") == getattr(observer, "model", None) \
                        and extraction.get("schema_version") == VISION_SCHEMA_VERSION and extraction.get("prompt_version") == VISION_PROMPT_VERSION:
                    skipped += 1; continue
                row = self.store.db.execute("SELECT artifact,metadata,uri,observed_at FROM raw_records WHERE source_id=? AND version=?", (doc.source.source_id, doc.source.version)).fetchone()
                if not row: continue
                payload = __import__("pathlib").Path(row["artifact"]).read_bytes()
                item = Input("local-files", doc.source.source_id, payload, row["uri"], doc.source.observed_at,
                             json.loads(row["metadata"] or "{}"))
                self._run_vision(item, doc); processed += 1
        finally:
            self.vision_observer = previous
        return {"processed": processed, "skipped": skipped}

    def ingest(self, item: Input, job_id: str) -> bool:
        source = source_version(item)
        event_id = hashlib.sha256((item.provider + "\x00" + item.tenant + "\x00" +
                                   item.connector + "\x00" + item.source_instance + "\x00" +
                                   item.external_id + "\x00" + source.version).encode()).hexdigest()
        audit_events = self.audit.all_audit() if hasattr(self.audit, "all_audit") else self.audit.all()
        if any(event.event_id == event_id for event in audit_events):
            if any(status in ("pending", "failed", "claimed") for _, status in self.ledger.outbox()):
                with self._writer: self.engine.process_outbox(worker="engine", failure=None)
                return True
            return False
        record = RawRecord(source, item.payload, item.metadata)
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
            if hasattr(self.ledger, "atomic_accept") and self.ledger.db is getattr(self.store, "db", None):
                event = AuditEvent(event_id, "ingest", job_id, doc.document_id)
                outcome = self.ledger.atomic_accept(
                    change,
                    before_append=(lambda db: self.store._save_raw_sql(db, record),),
                    after_append=(lambda db: db.execute("INSERT OR IGNORE INTO audit VALUES (?,?,?,?,?)", (event.event_id, event.action, event.actor, event.target, event.at.isoformat())),),
                )
                if outcome.value != "accepted":
                    pending = any(status in ("pending", "failed", "claimed") for _, status in self.ledger.outbox())
                    self.engine.process_outbox(worker="engine", failure=None)
                    return outcome.value == "duplicate" and pending
                self.engine.process_outbox(worker="engine", failure=None, raise_on_failure=True)
                self._run_vision(item, doc)
                self.engine.checkpoint()
                if refresh_within_grace:
                    self._suppressed.pop(doc.source.source_id, None)
                    self.engine.replay(rebuild=True)
                return True
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

    def search(self, query: str, identity, is_admin=False):
        legacy = not hasattr(identity, "subject")
        identity_name = identity if legacy else identity.subject
        admin = is_admin if legacy else identity.is_admin(identity.tenant)
        lexical = []
        for hit in self.index.search(query):
            doc = self.store.get(hit.document_id)
            suppressed_until = self._suppressed.get(doc.source.source_id) if doc else None
            suppressed = suppressed_until is not None and suppressed_until > datetime.now(timezone.utc)
            source = self._source_for(doc.document_id, doc.source.source_id) if doc else None
            tenant_ok = legacy or (source is not None and source.tenant == identity.tenant
                                   and identity.can_read(identity.tenant, doc.source.source_id))
            if doc and not doc.tombstoned and tenant_ok and doc.acl.permits(identity_name, admin) and not suppressed: lexical.append(hit)
        if not self.semantic_embedder or not self.semantic_model or not hasattr(self.store, "embedding_rows"):
            return lexical
        rows = self.store.embedding_rows(self.semantic_model)
        if not rows:
            return lexical
        try:
            query_vector = self.semantic_embedder.embed((query,))[0]
            semantic = []
            query_norm = sum(value * value for value in query_vector) ** 0.5
            if not query_norm: return lexical
            for row in rows:
                doc = self.store.get(row["document_id"])
                source = self._source_for(doc.document_id, doc.source.source_id) if doc else None
                if not doc or doc.tombstoned or (not legacy and (source is None or source.tenant != identity.tenant
                                                                  or not identity.can_read(identity.tenant, doc.source.source_id))) or not doc.acl.permits(identity_name, admin): continue
                if len(query_vector) != row["dimensions"]: continue
                suppressed_until = self._suppressed.get(doc.source.source_id)
                if suppressed_until is not None and suppressed_until > datetime.now(timezone.utc): continue
                try: vector = unpack_vector(row["vector"], row["dimensions"])
                except Exception: continue
                norm = sum(value * value for value in vector) ** 0.5
                score = sum(left * right for left, right in zip(query_vector, vector)) / (query_norm * norm) if norm else 0
                semantic.append((score, SearchHit(doc.document_id, doc.title, doc.text[:240], doc.source.source_uri, doc.source.version)))
            semantic.sort(key=lambda item: (-item[0], item[1].document_id))
            score_by_id = {}
            for rank, hit in enumerate(lexical, 1): score_by_id[hit.document_id] = score_by_id.get(hit.document_id, 0) + 1 / (60 + rank)
            for rank, (_, hit) in enumerate(semantic, 1): score_by_id[hit.document_id] = score_by_id.get(hit.document_id, 0) + 1 / (60 + rank)
            hits = {hit.document_id: hit for hit in lexical}
            hits.update({hit.document_id: hit for _, hit in semantic})
            return [hits[doc_id] for doc_id, _ in sorted(score_by_id.items(), key=lambda item: (-item[1], item[0]))]
        except Exception:
            return lexical

    def answer(self, query: str, identity: str, is_admin=False, max_evidence=8):
        hits = tuple(self.search(query, identity, is_admin)[:max_evidence])
        visual_documents = []
        evidence_items = []
        for number, hit in enumerate(hits, 1):
            document = self.store.get(hit.document_id)
            metadata = getattr(document, "metadata", {}) if document else {}
            extraction = self.store.image_extraction(document.source.source_id, document.source.version) if document and hasattr(self.store, "image_extraction") else None
            observation = None
            if extraction and extraction.get("status") == "success" and extraction.get("observation"):
                try: observation = validate_observation(json.loads(extraction["observation"]))
                except (TypeError, ValueError): observation = None
            is_visual = bool(metadata.get("mime_type") == "image/jpeg" or metadata.get("image_extraction"))
            if is_visual: visual_documents.append((hit, document))
            item = {"citation_id": f"E{number}", "_document_id": hit.document_id,
                    "title": str(hit.title)[:512], "snippet": str(hit.snippet)[:2048],
                    "provenance": self.search_metadata(hit).get("provenance", [])}
            if is_visual:
                item.update({"visual_evidence": True, "non_clinical": True,
                             "visual_observation": observation,
                             "visual_observation_provenance": {key: extraction.get(key) for key in
                                                                 ("status", "model", "schema_version", "prompt_version", "content_hash")}
                             if extraction else {"status": "unavailable"}})
            evidence_items.append(item)
        evidence = tuple(evidence_items)
        model_evidence = tuple({key: value for key, value in item.items() if key != "_document_id"} for item in evidence)
        try:
            raw_result = self.answerer.answer(query, model_evidence)
            result = validate_answer_result(raw_result, model_evidence,
                                            raw_result.get("provider", "unknown") if isinstance(raw_result, dict) else "unknown",
                                            raw_result.get("model", "unknown") if isinstance(raw_result, dict) else "unknown")
        except AnswerValidationError:
            # One deterministic repair attempt. Evidence tuple is reused byte-for-byte;
            # abstentions and provider availability failures never enter this branch.
            try:
                retry = getattr(self.answerer, "answer_with_context", None)
                context = ("RETRY: copy citation IDs exactly from supplied evidence. "
                           "Return grounded=true only when every claim has supplied citations; "
                           "otherwise return grounded=false with citations=[].")
                raw_result = retry(query, model_evidence, context) if retry else self.answerer.answer(query, model_evidence)
                result = validate_answer_result(raw_result, model_evidence,
                                                raw_result.get("provider", "unknown") if isinstance(raw_result, dict) else "unknown",
                                                raw_result.get("model", "unknown") if isinstance(raw_result, dict) else "unknown")
            except AnswerValidationError:
                if visual_documents: return self._visual_evidence_answer(visual_documents, evidence)
                raise
        except AnswerUnavailable:
            if visual_documents: return self._visual_evidence_answer(visual_documents, evidence)
            raise
        except Exception:
            if visual_documents: return self._visual_evidence_answer(visual_documents, evidence)
            raise
        if not result["grounded"] and visual_documents:
            return self._visual_evidence_answer(visual_documents, evidence)
        response = {"answer": result["answer"], "grounded": result["grounded"],
                    "citations": citation_dtos(result, evidence), "model": result["model"],
                    "provider": result["provider"]}
        if visual_documents: response["visual_evidence"] = True
        return response

    def _visual_evidence_answer(self, visual_documents, evidence):
        """Summarize persisted observations only; never invoke generic answerer."""
        evidence_by_id = {item.get("_document_id", item.get("document_id")): item for item in evidence}
        statuses, orientations, qualities = {}, {}, {}
        visible_text, markers_devices, uncertainty = [], [], []
        labels = {field: [] for field in LABEL_FIELDS}
        extracted = 0
        citations = []
        for hit, document in visual_documents[:8]:
            extraction = self.store.image_extraction(document.source.source_id, document.source.version) \
                if hasattr(self.store, "image_extraction") else None
            status = extraction.get("status", "unavailable") if extraction else "unavailable"
            statuses[status] = statuses.get(status, 0) + 1
            observation = None
            if status == "success" and extraction and extraction.get("observation"):
                try:
                    observation = validate_observation(json.loads(extraction["observation"]))
                except (TypeError, ValueError):
                    status = "invalid"
                    statuses["invalid"] = statuses.get("invalid", 0) + 1
            if observation is not None:
                extracted += 1
                orientations[observation["orientation"]] = orientations.get(observation["orientation"], 0) + 1
                qualities[observation["image_quality"]] = qualities.get(observation["image_quality"], 0) + 1
                for field, target in (("visible_text", visible_text), ("markers_devices", markers_devices), ("uncertainty", uncertainty)):
                    for value in observation[field]:
                        if value not in target and len(target) < 8: target.append(value[:128])
                for field in LABEL_FIELDS:
                    for candidate in observation["label_candidates"][field]:
                        value = candidate["candidate"]
                        if value not in labels[field] and len(labels[field]) < 8: labels[field].append(value[:128])
            citation = dict(evidence_by_id[hit.document_id])
            citation.pop("_document_id", None)
            citation.pop("citation_id", None)
            citation.update({"label": "automated visual observation", "extraction_status": status,
                             "extraction": {key: extraction.get(key) for key in
                                             ("model", "schema_version", "prompt_version", "content_hash")}
                             if extraction else None})
            citations.append(citation)
        summary = {"document_count": len(visual_documents[:8]), "extracted_count": extracted,
                   "extraction_status_counts": statuses, "orientation_counts": orientations,
                   "image_quality_counts": qualities, "visible_text": visible_text,
                   "markers_devices": markers_devices, "uncertainty": uncertainty,
                   "label_candidates": labels}
        grounded = extracted > 0
        return {"answer": "Automated visual observation summary; source observations only." if grounded
                else "No validated visual observation is available.",
                "grounded": grounded, "visual_evidence": True, "summary": summary,
                "citations": citations, "model": "none", "provider": "deterministic-local"}

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
        with self.ledger._lock:
            row = self.ledger.db.execute(
                "SELECT source FROM protocol_ledger "
                "WHERE object_id=? AND operation<>? "
                "ORDER BY sequence DESC LIMIT 1",
                (document_id, Operation.DELETE.value),
            ).fetchone()
        return IdentityNamespace(*json.loads(row[0])) if row else None

    def _ledger_sequence(self, document_id, source):
        with self.ledger._lock:
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
        checkpoints["default:document"] = checkpoints.get("default:state", 0)
        checkpoints["default:search"] = checkpoints.get("default:lexical", 0)
        lag = {k: max(0, latest-v) for k,v in checkpoints.items()}
        return {"ledger_sequence": latest, "outbox_pending": sum(status in ("pending", "claimed", "failed") for _, status in outbox), "outbox_failed": sum(status == "failed" for _, status in outbox), "dead_letters": len(ledger.dead_letters()) if hasattr(ledger, "dead_letters") else 0, "gaps": len(ledger.gaps()) if hasattr(ledger, "gaps") else 0, "checkpoints": checkpoints, "watermarks": {"document": checkpoints["default:document"], "search": checkpoints["default:search"]}, "projection_lag": lag, "max_projection_lag": self.max_projection_lag, "metrics": {"ledger_appends": latest, "outbox_total": len(outbox), "checkpoint_streams": len(checkpoints)}}

    def readiness(self):
        try:
            self.store.status(); health = self.health()
            lag_ready = all(value <= self.max_projection_lag for value in health["projection_lag"].values())
            ready = health["gaps"] == 0 and health["dead_letters"] == 0 and lag_ready
            return {"status": "ready" if ready else "not_ready", "checks": {"storage": True, "replay": ready, "projection_lag": lag_ready}, "health": health}
        except Exception as exc:
            return {"status": "not_ready", "checks": {"storage": False}, "error": type(exc).__name__}

    def report(self, principal=None):
        """Return stable, read-only aggregate metrics for authenticated operators."""
        if principal is not None and (not hasattr(principal, "is_admin") or not principal.is_admin(principal.tenant)):
            raise PermissionError("admin principal required")
        status = self.store.status()
        health = self.health()
        readiness = self.readiness()
        return {
            "counts": {
                "documents": status["documents"],
                "tombstones": status["tombstones"],
                "raw_records": status["raw_records"],
            },
            "ledger": {
                "sequence": health["ledger_sequence"],
                "outbox_pending": health["outbox_pending"],
                "outbox_failed": health["outbox_failed"],
                "dead_letters": health["dead_letters"],
                "gaps": health["gaps"],
                "checkpoints": health["checkpoints"],
            },
            "projection": {
                "lag": health["projection_lag"],
                "max_lag": health["max_projection_lag"],
                "watermarks": health["watermarks"],
            },
            "readiness": {
                "status": readiness["status"],
                "checks": readiness.get("checks", {}),
            },
        }
