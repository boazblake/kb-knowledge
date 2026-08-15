# Phase 1 Architecture Decision

```text
+--------------------------------------------------------------+
| STATUS: DIRECTION LOCKED                           PROD: NO-GO|
| DONE: Python contracts; authority boundary; hardening sequence |
| OPEN: budgets; ADR details; owners; OpenSearch trigger metrics |
| BLOCKERS: real OIDC/KMS; PostgreSQL authority; purge; recovery|
| NEXT: build pgvector+PostgreSQL FTS baseline; prove gates      |
+--------------------------------------------------------------+
```

## Research record standard

- Full findings remain below; this record adds status and current-direction context without deleting substantive material.
- Record metadata must name agent role, date, source or source set, and validation owner.
- Label agent findings separately from recommendations. Article claims, where present, must remain separate from recommendations and repository facts.
- Keep unresolved decisions explicit. No silent resolution, inference, or acceptance approval is allowed.

### Current locked direction

Initial retrieval uses **pgvector plus PostgreSQL full-text search** over rebuildable derived projections. PostgreSQL remains authority. Reconsider **OpenSearch later** only when measured scale, query latency, operational isolation, or retrieval features exceed the PostgreSQL design envelope. This records current direction without deleting historical Phase 1 recommendations below.

> **Provenance:** Architect agent; Phase 1; 2026-08-15; validation owner: Parent.
>
> **Editorial note:** **Agent finding** sections preserve architecture findings. Ordering, tables, and recovery limits are editorial organization. Conflicting search recommendations remain conflicting.

## Decision

**Agent finding.** Keep Python adapter/orchestrator initially. Replace commodity infrastructure behind stable Python contracts. Do not rewrite in Go yet. Harden before production; production remains **NO-GO** until product gates pass.

## Target stack

| Concern | Target |
|---|---|
| Approved application connector and OAuth sync | Nango |
| Accepted knowledge state and authority | PostgreSQL |
| Raw bytes | S3-compatible object storage |
| Durable projection trigger | PostgreSQL transactional outbox plus CDC/relay |
| Durable workflows | Temporal |
| Initial hybrid index and retrieval | **pgvector plus PostgreSQL full-text search** |
| Later retrieval expansion trigger | OpenSearch only after measured scale, latency, isolation, or feature trigger |
| Parsing | Docling, Tika, or Unstructured behind parser contracts |
| Model | Ollama behind model ports; never authority |
| Identity | OIDC |
| Key management | KMS |
| Observability | OpenTelemetry |

## Authority boundary

**Agent finding.** Sources own source truth. PostgreSQL owns accepted knowledge state. Object storage owns raw source bytes. Indexes are derived, rebuildable projections. Ollama is non-authoritative. Python owns semantic policy, contract enforcement, provenance, citation, and thin API behavior.

## Core flows

### Ingestion

Connector authenticates through OIDC/OAuth integration, reads source changes, records stable source identity and cursor, stores raw bytes in object storage, and writes accepted metadata/state to PostgreSQL. Transactional outbox emits projection work. Temporal coordinates retries, idempotency, timeout, and recovery.

### Projection

CDC/relay consumes durable outbox changes. Parser adapter extracts text and metadata. Chunk adapter creates stable chunks with source and document provenance. Index adapter projects searchable and vector representations into PostgreSQL-backed derived indexes. Projection failure does not rewrite authority; replay rebuilds derived state. OpenSearch remains a later option after its trigger is measured.

### Query and answer

Python policy layer authenticates caller, evaluates tenant/source authorization with deny-by-default behavior, queries only authorized PostgreSQL FTS and pgvector projections, and returns provenance and citations. Ollama receives permitted context through model port. Answer layer abstains when evidence is insufficient. Model output cannot grant access or become source truth.

### Purge

Policy determines retention and purge eligibility. Workflow records purge intent and evidence in PostgreSQL, removes raw bytes, accepted state, and derived projections, and verifies completion across stores. Retries remain idempotent. Missing or unverifiable deletion blocks completion and surfaces operationally.

## Adapters and custom responsibilities

**Agent finding.** Commodity adapters cover connector, storage, parser, workflow, index, identity, KMS, model, and telemetry integrations. Custom code remains responsible for semantic policy, authority transitions, provenance, citation, thin API contracts, deny-by-default ACL evaluation, purge semantics, and evidence. Stable contracts isolate provider changes.

## Migration, shadow, cutover, rollback

**Agent finding.** Migration order:

1. Replace fake ACL and fake OIDC.
2. Replace fake KMS.
3. Move authority from SQLite to PostgreSQL.
4. Replace local connector with Nango-backed approved connector.
5. Replace custom parser and index with adapter-backed components.
6. Replace or harden backup and recovery.
7. Put Ollama behind model ports; remove direct integration.

Use shadow operation before cutover. Compare authorization, provenance, retrieval, purge, and operational evidence. Cut over by bounded capability. Keep rollback path to prior projection or adapter while PostgreSQL authority remains canonical. Do not call cutover production-ready until SEC, ING, ANS, PUR, and OPS gates pass.

## Consistency model

**Agent finding.** PostgreSQL transaction commits accepted state and outbox event atomically. CDC/relay and projections are eventually consistent. Query path must expose or enforce freshness expectations; missing projection must never be treated as authorization. Replay repairs derived state.

## Failure ownership

**Agent finding.** Source, authority, object store, relay, parser, index, workflow, identity, KMS, and model adapters each own their failures and emit actionable evidence. Projection failures do not rewrite authority. Adapter contracts and replay provide recovery boundary.

## Observability and budgets

**Agent finding.** Instrument ingestion, projection, query, answer, purge, authorization, storage, workflow, and adapter boundaries with OTel. Export metrics to Prometheus and dashboards/alerts to Grafana. Establish and validate performance budgets, load targets, SLOs, RPO, and RTO before production approval. Phase 1 did not supply values; they remain unresolved.

## Required ADRs and contracts

**Agent finding.** Create ADRs for:

- search/index selection;
- authority and consistency;
- purge evidence;
- identity/policy enforcement;
- connector ownership;
- model boundary.

Add mandatory contract tests for every adapter. End-to-end tests must cover ACL denial, provenance/citation, abstention, purge, replay, recovery, and rollback.

## Explicit unresolved search decision

**Agent finding.** Architect recommends **OpenSearch as initial target** for hybrid retrieval. Product manager recommends **pgvector default**; librarian also recommends pgvector default, with Qdrant at vector scale. Recommendations conflict. Record unresolved Phase 2 decision. PostgreSQL remains authority regardless of selected retrieval index.

**Current locked direction.** Initial retrieval uses **pgvector plus PostgreSQL full-text search**. OpenSearch is deferred until a measured scale, latency, operational-isolation, or retrieval-feature trigger is recorded. Historical conflicting recommendations remain preserved; this explicit entry prevents silent resolution.

## Production boundary

**Agent finding.** Architecture recommendation is not production approval. Product SEC, ING, ANS, PUR, and OPS gates must pass, including real OIDC/KMS, authoritative persistence, verified purge, recovery evidence, load/service objectives, explicit RPO/RTO, and approvals.

## Recovery limits

Full architect terminal transcript containing any additional flow diagrams, adapter contract fields, failure matrix, numeric budgets, ADR details, or migration evidence not represented above was unavailable in workspace context. Missing content cannot be safely reconstructed; no contradiction was silently resolved.
