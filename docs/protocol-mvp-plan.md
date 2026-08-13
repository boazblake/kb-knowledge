# Protocol MVP plan

## Status

Phase 5 establishes stable protocol boundaries without claiming full BII delivery.
Local synthetic protocol-demo is usable for contract demonstrations. QA/BDD/SRE
evidence uses checked-in test-manifest provenance. Real-data pilot is **NO-GO**.

## Stable spine

`IdentityNamespace` scopes provider, tenant, and subject. `Envelope` carries versioned
transport metadata. `CanonicalChange` carries source, revision, operation,
idempotency, provenance, permissions, and data class. `Ledger`, `KnowledgeStore`,
`Projection`, `Retriever`, query/evidence types, and `CompositionManifest` define
implementation seams. `KnowledgeEngine` provides reference append/apply/replay.

Exact `ObjectKey` is `(provider, tenant, connector, source_instance, object_id)`.
Duplicate delivery is idempotent. Conflicting same-revision payloads and revision gaps
are quarantined; recovery supplies missing revision, then retries higher revision.
Reference state and projections use tenant/object boundaries. Capability versions and
features are checked through `CompositionManifest`. Gate 1 uses encrypted payload
envelopes with erasable DEKs; purge erases DEK. Freshness: 5m local, 15m external.
Loopback reader/admin identities are short-lived demo identities.

## Reused reference adapters

| Boundary | Current reference |
|---|---|
| Acquire | `LocalFilesConnector` |
| Canonicalize | `PlainTextCanonicalizer` |
| Durable local state | `SQLiteStore` / `MemoryDocumentStore` alias |
| Protocol ledger | `RelationalReferenceLedger` |
| Current state | `CurrentStateStore` |
| Projections | `StateProjection`, `DocumentProjection`, `RelationshipProjection`, `LexicalProjection` |
| Search | `LexicalIndex` and SQLite FTS5 |
| Policy/evidence | injected ACL resolver, `PermissionState`, `ProvenanceLink`, audit stores |

These adapters demonstrate composition. They do not provide production guarantees.

## Composition and target diagram disposition

Provider SDKs stop at Connector/Canonicalizer. Storage, ledger, projections, search,
identity, model, and output implementations enter through contracts and dependency
injection. No composition root, supported launcher, production identity provider, or
deployment configuration exists.

Implemented/reference nodes: local input, raw/envelope/change boundary, plaintext
canonicalization, canonical document path, SQLite state/raw/FTS5, lexical search,
ACL/tombstone/revocation filtering, capability checks, and API handler factory.

Deferred or partial nodes: connector scheduling/watch/resume, authoritative ledger,
durable outbox, crash-safe replay/checkpoints, complete purge/recovery, real
identity/access, observability, parse/extract/chunk/embed, vectors, relationships,
and production API/UI integration. Email, CRM, drives, databases, MCP, agents, chat,
models, and other output consumers remain target nodes only.

## NO-GO exit work

1. Ledger authority and durable outbox.
2. Namespace and authenticated authorization isolation.
3. Replay and checkpoint recovery after crash/concurrency faults.
4. Purge across raw, projections, backups, caches, and recovery artifacts.
5. Supported API/UI composition, auth, hosting, and route contract.
6. Readiness, metrics, logs, tracing, alerts, capacity, and on-call operation.
