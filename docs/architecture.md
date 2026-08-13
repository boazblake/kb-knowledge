# Architecture and implementation map

## Authority and status

`BII.md` and `pipelineflow.png` describe target architecture. This page describes
checked-in behavior. Phase 5 protocol spine is reference-only. QA/BDD/SRE evidence
uses checked-in test-manifest provenance. Real-data pilot: **NO-GO**.

## Delivered runtime

```text
local files -> LocalFilesConnector -> RawRecord -> PlainTextCanonicalizer
             -> injected ACL -> CanonicalDocument -> KnowledgeService/KnowledgeEngine
             -> SQLiteStore or RelationalReferenceLedger -> state/document/relationship/lexical projections
             -> FTS5 or LexicalIndex -> ACL/tombstone/revocation-filtered search
             -> API handler (/v1/*) or static UI assets
```

`SQLiteStore` persists documents, raw payload files, FTS5 rows, tombstones,
revocations, checkpoints, and audit records. `KnowledgeEngine` provides reference
append/apply/replay with `CanonicalChange`, `Ledger`, state, projections, and
capability contracts. These paths are not one authoritative production write model.

## Target diagram node mapping

| Diagram node | Phase 5 state | Evidence / boundary |
|---|---|---|
| Local-file input | Implemented | `LocalFilesConnector`; scan-limit and incomplete-scan safety |
| Email, CRM, drives, DB, etc. | Deferred | Contracts only |
| Connector acquire changes | Partial | Recursive scan only; no scheduler, watch, resume, or outbox |
| Raw records | Implemented boundary | RawRecord/envelope/change contracts; SQLite raw path |
| Canonicalizer | Partial | UTF-8 plaintext only; no MIME/attachments |
| Canonical model | Reference spine | CanonicalChange, namespace, revision, permission/provenance links |
| Knowledge engine/store | Reference | SQLiteStore and relational ledger; no authoritative ledger/outbox |
| Index/search | Demo | FTS5 and LexicalIndex; vector search deferred |
| Security | Partial/demo | Injected ACL and filtering; no production auth isolation |
| Provenance | Partial | URI and payload hash; incomplete transformation/citation chain; freshness 5m local/15m external |
| Query/API | Partial | Factory and `/v1/health`, `/v1/status`, `/v1/search`; no launcher |
| Web UI | Deferred integration | Static shell; no supported host/token/composition path |
| MCP, agents, chat, applications | Deferred | No implementations |
| Observability | Deferred | No readiness, metrics, logs, tracing, or alerts |
| Backup/resilience | Partial/unsafe | Copy/restore utility; no atomicity, RPO/RTO, or rehearsal |

## Composition and semantics

Provider SDKs stop at Connector/Canonicalizer. Storage, ledger, projections, search,
identity, models, and outputs enter through contracts and dependency injection.
`CompositionManifest` checks capability compatibility. Duplicate delivery is
idempotent; conflicting same-revision changes and revision gaps are quarantined; missing revisions must arrive before higher revisions recover; reference state uses
tenant/object boundaries.

Index, store, audit, raw, and ledger effects are not one transaction. No durable
outbox coordinates them. Replay/checkpoint methods demonstrate contracts, not
crash-safe bounded multi-stream recovery. Reference purge removes local raw/current/
search state; external adapter deletion is not claimed.

## Non-goals

No production identity, encryption, concurrency safety, durable outbox, source-scoped
deletion proof across all artifacts, monitoring, limits policy, email/attachments,
semantic search, model providers, supported API/UI integration, or deployment exists.
