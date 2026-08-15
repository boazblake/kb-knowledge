# Architecture and implementation map

## Authority and status

`BII.md` and `pipelineflow.png` describe target architecture. This page describes
checked-in behavior. Security boundaries include immutable Principal/AuthZ ports,
fake OIDC/JWKS validation, and fake KMS AEAD envelopes with context, rotation, and
erasure. Production guards reject fake providers. Phase 5 protocol spine is reference-only. QA/BDD/SRE evidence
uses checked-in test-manifest provenance. Gate 2/3 QA records **66/66 serial tests passing twice**, **15/15 targeted tests passing**, Python **3.11.12**, compile/Node/launcher smoke passing, and dynamic-port isolation. Evidence is complete for demo/reference scope, not production-cleared. Real-data pilot: **NO-GO**.

Gate 6 SRE evidence is recorded in [`GATE6_SRE_RESULTS.json`](../GATE6_SRE_RESULTS.json).
Synthetic local measurements reached ingest **694.8 records/s**, search **876.5 RPS**
at p95 **1.179 ms**, replay **2607 records/s**, backup **5.6 ms**, restore **12.1 ms**,
and **20/20 API readers** returned HTTP 200. These are not production guarantees.
Historical direct SQLite reader and serialized-writer probes exited with signal 11;
current reference access serializes shared connections and readiness fails document
lag above configured `max_projection_lag`. Evidence used unsupported Python **3.9.6** versus
`pyproject.toml` **>=3.11**, and no numeric SLO/RPO/RTO targets exist. Gate 6 therefore
failed production qualification. Real-data status remains **NO-GO**.

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

## Synthetic Nango adapter experiment

`kb_pipeline.nango_adapter` is a deliberately narrow, deterministic adapter
experiment. It maps Nango-like poll and webhook fixtures into paired
`RawRecord`/`CanonicalChange` envelopes with exact `ObjectKey` identity:
provider config, tenant, connector, source instance/connection, and object ID.
Run, cursor, source revision/hash, operation, permissions, retry class, and
capability metadata remain explicit. Local ledger remains authority: caller
must acknowledge durable append before cursor advancement. Incomplete snapshots
never infer deletes. Adapter writes no ledger, projection, or archive. Retention
is therefore limited to the local ledger policy; remote archive/retention is
not claimed. Capability set is partial/degraded when source permissions or
reconciliation completeness are unavailable.
| Knowledge engine/store | Reference | SQLiteStore and relational ledger; no authoritative ledger/outbox |
| Index/search | Demo | FTS5 and LexicalIndex; vector search deferred |
| Security | Reference boundary / fake-only adapters | Immutable Principal/AuthZ ports; fake OIDC/JWKS; fake KMS AEAD context/rotation/erasure; production guards; no real integrations |
| Provenance | Partial | URI and payload hash; incomplete transformation/citation chain; freshness 5m local/15m external |
| Query/API | Partial | Local launcher and `/v1/health`, `/v1/status`, `/v1/search`; no supported production deployment |
| Web UI | Deferred integration | Static shell; no supported host/token/composition path |
| MCP, agents, chat, applications | Deferred | No implementations |
| Observability | Partial / not production-qualified | Readiness and metrics expose document/search watermarks and fail above configured lag; no production logs, tracing, or alerts |
| Backup/resilience | Partial/unsafe | Copy/restore utility and encrypted raw persistence tests; no decryption read path, canonical ledger encryption migration, atomicity, RPO/RTO, or rehearsal |

Experiment status: **EXPERIMENT only**, not production adoption. Local ledger remains authority; Nango cache is not an archive. Revisions, raw retention, permissions, replay, purge, and credentials remain unresolved. Dynamic-port isolation fixes covered test collision; it does not prove production concurrency.

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

## Security boundary scope and remaining gaps

Fake OIDC/JWKS and fake KMS exist only for deterministic tests and local reference
composition. They do not establish network JWKS refresh, real KMS calls, credentials,
or operational key custody. Encrypted raw persistence tests verify write-side envelope
use and plaintext-fallback rejection; read-side decryption and canonical ledger
encryption migration remain open. Deployment/operations, load, and measured RPO/RTO
also remain open. No production data may enter system.

## Non-goals

No real OIDC/KMS integration, production identity, canonical ledger encryption,
decryption read path, concurrency safety, durable outbox, source-scoped
deletion proof across all artifacts, monitoring, limits policy, email/attachments,
semantic search, model providers, supported API/UI integration, or deployment exists.

Next actions: rerun SQLite reader/writer concurrency and readiness document-lag evidence;
rerun under supported Python **>=3.11**; define numeric SLO/RPO/RTO targets; repeat
Gate 6 evidence. Keep real-data pilot **NO-GO**.
