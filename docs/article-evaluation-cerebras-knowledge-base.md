# Cerebras knowledge-base article evaluation

```text
+--------------------------------------------------------------+
| STATUS: EVALUATION COMPLETE                       PROD: NO-GO |
| DONE: claims; mappings; gaps; pgvector+PostgreSQL FTS choice  |
| OPEN: retention/roles/threshold owners; OpenSearch trigger     |
| BLOCKERS: real OIDC/KMS; authority; purge; recovery; approvals|
| NEXT: harden first; validate baseline; record trigger metrics  |
+--------------------------------------------------------------+
```

## Research record standard

- Full findings remain below; this record adds status and current-direction context without deleting substantive material.
- Record metadata must name agent role, date, source or source set, and validation owner.
- Keep article claims separate from repository facts and recommendations. Article claims are not independently verified here and do not become requirements by implication.
- Keep unresolved decisions explicit. No silent resolution, inference, or acceptance approval is allowed.

### Current locked direction

Initial retrieval uses **pgvector plus PostgreSQL full-text search**. PostgreSQL remains authority. Reconsider **OpenSearch later** only after measured scale, query latency, operational isolation, or retrieval-feature limits exceed the PostgreSQL design envelope. Hardening comes first; production remains **NO-GO**.

> **Evaluation status:** Complete findings, not a product approval.
> **Canonical article:** <https://www.cerebras.ai/blog/how-we-built-our-knowledge-base>
> **Authors:** Isaac Tai, Daniel Kim, Mike Gao
> **Published:** 2026-07-15
> **Access date:** 2026-08-15
> **Evaluation confidence:** High for article claims preserved below; medium for mapping those claims to this repository; unresolved details are marked.

## Reading boundary

This document separates three kinds of information:

- **Article claim** — what Cerebras says it built or observed. It is not independently verified here.
- **Repository fact** — behavior, scope, or decision recorded in checked-in Phase 1 and architecture documents.
- **Recommendation** — proposed adaptation for this pipeline. It is not an article claim and does not override Phase 1 gates.

Article performance, adoption, accuracy, and implementation claims remain Cerebras-reported. They are useful design evidence, not acceptance evidence for this project.

## Executive finding

Cerebras built a multi-source knowledge product around one queryable Postgres embeddings table, source-specific connectors, normalized/distilled records, hybrid retrieval, and an answer layer. Slack receives special treatment: complete threads are re-ingested, distilled into question/summary/resolution artifacts, and supplemented with high-signal burst embeddings. Code uses language-aware recursive chunking and incremental synchronization. Query planning fans out to source-specific tools, while projects constrain default scope.

The strongest transferable idea is not “put everything in a vector database.” It is a projection model: preserve source-native systems, normalize each source into a common retrieval contract, combine lexical and semantic evidence, then package citations and context only after authorization and ranking.

This pipeline already has several compatible foundations: canonical changes, provenance-shaped records, lexical search, ACL filtering, tombstones, revocations, replay-shaped contracts, and a canonical-object/document-projection model. It lacks production authority, real identity and key management, approved external connectors, semantic indexing, complete purge evidence, and MCP/planner/project consumers.

**Decision:** For initial target, use **pgvector plus PostgreSQL full-text search**. Keep PostgreSQL as authority and use derived vector/FTS projections. Revisit **OpenSearch later** only when a bounded trigger is met: measured scale, query latency, operational isolation, or retrieval features exceed the PostgreSQL design envelope. This resolves the Phase 1 search conflict for initial scope; it does not reject OpenSearch permanently.

**Hard boundary:** Hardening first. Real-data pilot remains **NO-GO** until SEC, ING, ANS, PUR, and OPS gates pass. Article-inspired features cannot bypass real OIDC, real KMS, authoritative persistence, verified purge, recovery evidence, numeric SLO/RPO/RTO, or named approvals.

## Article architecture and product

### Product shape

**Article claim.** Cerebras Knowledge launched three months before article publication, receives more than 15,000 internal questions per day, and is used by people, automations, and agents. It serves a company spanning data-center operations, chip design, hardware, training, inference, and cloud platform. Its purpose is to connect people and systems to useful internal information without requiring teams to move work into one new system.

**Article claim.** Product has three layers:

1. Collect and store internal data.
2. Query collected data.
3. Enforce authentication and authorization, with auditing and analytics.

**Recommendation.** Treat these as separate contracts in this repository. The query layer may consume derived indexes, but Python policy must authorize before retrieval and answer generation. Auditing must record decision and evidence. Analytics must not become an authority source.

### Common storage interface

**Article claim.** A single Postgres table holds embeddings, raw summaries, and metadata from many sources. Every connector emits rows with the same interface. Sources named in article diagrams include Slack, wiki/Confluence, code repositories, netlists, PRM documents, and custom databases. Each source defines its connection, content mapping, and fetch cadence. Rows become queryable through one interface.

**Recommendation.** Adapt this as a derived `document_projection`/`embedding_projection`, not as replacement for canonical authority. Preserve `tenant_id`, source identity, document identity, revision, timestamps, ACL references, provenance, content/summary, chunk identity, embedding model/version, and projection status. PostgreSQL remains transactional system of record; object storage remains raw-byte authority where applicable; indexes remain rebuildable.

**Repository fact.** `BII.md` already distinguishes canonical objects from retrieval documents and describes relational, document, graph, full-text, chunk, and embedding projections. Current runtime uses SQLite/FTS5 and local files. External sources, vector storage, production identity, and production projection coordination remain absent.

## Ingestion, Slack, distillation, burst, and code paths

### Source ingestion

**Article claim.** The system meets information where it lives. It does not force Slack, code, documents, incidents, or custom databases into one authoring platform. Developers can add custom connectors. The common row contract makes source-specific acquisition invisible to downstream query paths.

**Recommendation.** Keep provider SDKs behind connector and canonicalizer contracts. Connector contract must preserve stable identity, cursoring, revisions, permissions, retries, rate limits, deletion signals, and provenance. Use Nango for approved application OAuth/sync as Phase 1 library research recommends; do not treat article-style plugin scripts as production security or lifecycle controls.

### Slack real-time path

**Article claim.** Slack uses a bot in Socket Mode. Slack pushes message events over a persistent WebSocket. On event receipt, the service immediately acknowledges, deduplicates by stable event ID, and marks the message for an ingest consumer.

**Article claim.** Consumer resolves the message’s parent thread and fetches the complete conversation from Slack, including parent and replies. It writes the whole thread as one row. A reply therefore re-pulls parent and siblings, keeping content, participant list, and last-activity timestamp current. Each channel is a distinct data source, allowing per-channel freshness tuning.

**Recommendation.** Reuse the behavior as an ingestion reference pattern, not a current implementation commitment. First implement durable event receipt, idempotency, cursor/watermark, incomplete-snapshot safety, permission capture, and source-scoped deletion. Do not add Slack while fake identity/KMS and pilot blockers remain open.

### Slack lexical and semantic signals

**Article claim.** Raw Slack text is immediately keyword-searchable through PostgreSQL full-text search with a GIN index. Distillation adds semantic retrieval. Article identifies four complementary signals:

- Full-text catches exact error strings, flag names, and host names.
- Embeddings catch paraphrases with different vocabulary.
- IDF separates rare, informative tokens from filler.
- Age decay favors newer answers when relevance is otherwise comparable.

Each scorer produces a ranked view. No single scorer is trusted alone.

**Recommendation.** Initial retrieval should implement PostgreSQL FTS plus pgvector. IDF and recency should be explicit, testable features, not hidden LLM judgments. Apply tenant/source ACL and tombstone/revocation filters before result limits and context expansion.

### Distillation path

**Article claim.** Raw thread text is not embedded directly. An LLM receives the full thread and extracts a normalized artifact containing:

- one-line question an engineer would search;
- short summary;
- resolution;
- systems mentioned;
- code references.

The normalized question, summary, resolution, systems, and code references are embedded and written with source, channel, authors, and time metadata. Article reports materially better accuracy than embedding raw transcripts directly.

**Recommendation.** Make distillation an optional derived artifact with lineage to source revision and model/prompt version. Store raw source and extracted artifact separately. Failed or non-deterministic distillation must not block source acceptance or alter authority. Citation must point to source thread/message ranges, not only generated summary.

### Burst embeddings

**Article claim.** Thread-level summaries can omit an important tangent. Cerebras creates a “burst” from consecutive messages by one author, prepends thread topic as context, and embeds qualifying bursts alongside thread records.

**Article claim.** Burst must pass a signal threshold. Article lists these conditions: at least one relatively rare corpus token with IDF ≥ 4.0; combined burst length ≥ 200 characters; or one or more messages with reactions providing social signal. The diagram and prose describe a weighted combination; exact weights are not supplied. Short common-token bursts without reactions are filtered; longer rare-term/reacted bursts are embedded.

**Recommendation.** Treat thresholds as article-informed starting hypotheses, behind configuration and evaluation. Do not hard-code IDF 4.0 or 200 characters as universal truth. Add burst lineage, author/channel ACL, source offsets, and duplicate suppression. Evaluate recall, low-signal rate, storage cost, and purge completeness before enabling.

### Code repository path

**Article claim.** Cerebras initially questioned code embeddings because grep is useful. It adopted them after industry experimentation, including Cursor findings, because semantic code retrieval helps across many large repositories. Some repositories exceed 40 GB.

**Article claim.** CocoIndex maintains code embeddings. Language-specific regex boundaries are tried from coarse to fine: classes, then methods, then smaller blocks if a chunk remains too large. A file can create multiple specificity levels, such as file and function records. Changed commits re-embed and export only changed chunks. CocoIndex keeps synchronization metadata in Postgres.

**Article claim.** Repository onboarding is configuration-driven. Teams submit allowlists and denylists at file-path level.

**Recommendation.** Code indexing is later scope, not MVE. First define generic chunk/projection contracts and changed-revision replay. If adopted, preserve file/function identity, commit, language, path policy, source ACL, and chunk boundaries. Never infer that code embeddings replace ripgrep or source-of-truth repository access.

### Custom data sources

**Article claim.** Teams can submit a small Python plugin that reads an existing database and emits rows shaped like the shared embeddings table, plus a data-source entry. Downstream retrieval needs no special handling.

**Recommendation.** Our stable Python adapter boundary supports this shape, but arbitrary plugin execution is not acceptable as a production trust boundary. Require reviewed packages, capability declarations, secret isolation, timeout/retry policy, schema validation, provenance, deletion behavior, and owner metadata. Nango remains approved app-sync direction; Airbyte is for warehouse/ELT, not automatic replacement.

## Retrieval architecture

### Storage and indexing

**Article claim.** Embeddings use 3,072 dimensions in pgvector with HNSW. Raw content uses PostgreSQL FTS with GIN. One shared table carries source metadata and timestamps.

**Recommendation.** Use pgvector plus Postgres FTS for initial target. Select embedding model and dimension through a versioned model port; article’s 3,072 dimensions are not a requirement. Build HNSW only after validating memory, build time, recall, filtered-query behavior, and tenant isolation. Keep model/version and index version in projection metadata so rebuilds are possible.

### Six-list retrieval and fusion

**Article claim.** Retrieval runs six lists in parallel. Article diagrams show vector and lexical retrieval across source families, including thread summaries, wiki vector, Slack FTS, code/graph-like retrieval, and the unified search path. Exact internal list composition is diagrammatic rather than a formal API.

**Article claim.** Candidate lists are merged with reciprocal rank fusion. For document `d`, article gives `score(d) = Σ weight / (60 + rank(d))`, default weight 1.0 and smoothing constant `K = 60`. RRF rewards consensus across lists over one isolated high score. Duplicate chunks are merged to one source, per-file contribution is capped, and a diverse top twenty is formed.

**Recommendation.** Implement a small, deterministic fusion module with named retriever IDs, weights, `K`, duplicate/source grouping, and per-source caps. Record intermediate rankings for evaluation. Do not claim six retrievers until each has an owner and evidence. Initial MVE can start with two lists: Postgres FTS and pgvector.

### Reranking and context expansion

**Article claim.** A small reranker receives original query and fused candidates, scores each from 0–10, and retains top ten. After ranking, system expands context around winners. For a matched wiki section, it retrieves two neighboring sections so heading, preconditions, and caveats are not lost. Search output is an evidence packet: fused, deduplicated, reranked, and context-expanded.

**Recommendation.** Context expansion occurs after authorization and final candidate selection. Expansion must re-check ACL, tombstone, revision, and source deletion state. Store parent/neighbor relationships and offsets. Bound token count, neighbor count, source contribution, and latency. Citation must distinguish matched chunk from expanded context. Reranking remains deferred until baseline FTS/vector retrieval is measured.

## Planner, executor, MCP, and projects

### Planner and executor

**Article claim.** Each query starts with a short LLM planning pass. Planner sees compact descriptions of indexed projects, available sources, and source strengths. It selects tools. Executor fans calls out in parallel, normalizes outputs into a common evidence format, and passes evidence to final synthesis.

Named tools:

- `subsystem_index` — per-file LLM summaries;
- `search` — unified vector pipeline across sources, internally merged/reranked;
- `search_slack` — direct Slack retrieval;
- `search_code` — ripgrep over repositories;
- `recent_prs` — relevant recent pull requests;
- `who_knows` — people with demonstrated topic expertise.

**Recommendation.** Planner must be advisory and bounded. It cannot grant access, widen tenant/project scope, bypass retrieval policy, or make unsupported claims. Executor should use typed tool schemas, deadlines, cancellation, partial-result policy, and evidence provenance. Deterministic direct search remains available when planner fails.

### MCP

**Article claim.** MCP exposes retrieval primitives as direct, narrow, structured, mostly LLM-free tools. Examples include `search`, `search_slack`, `search_code`, and `who_knows`. Tools run one retrieval pipeline, apply lightweight scoring, and return raw evidence rows. MCP clients such as Claude Code orchestrate tool calls and assemble answers or edits.

**Recommendation.** MCP is deferred from initial content scope in Phase 1. Later MCP tools must expose only authorized evidence, stable schemas, source citations, freshness, and refusal/error states. Keep orchestration outside retrieval tools. Do not expose a generic unrestricted “answer” tool as first integration.

### Web UI

**Article claim.** Web UI connects same tools to end-to-end planner → parallel executor → synthesis flow. Planner chooses tools for query and active project. Executor returns typed evidence with scores, recency, and source hints. Final LLM produces answer, citations, caveats, and cross-source synthesis.

**Repository fact.** Current UI/API path is local/reference scope. Supported production hosting, production identity/token path, and composition remain absent. Local generated answers require explicit Ollama opt-in and citations; deterministic abstention is default.

### Projects and default scope

**Article claim.** “Search everything” became noisy. A project is a named bundle of relevant Slack channels, repositories, databases, and document spaces. One source can belong to several projects without duplication. New users select or create a default project; profile default scopes queries automatically.

**Recommendation.** Projects are useful scope and relevance controls, but not substitutes for tenant/source authorization. Store project membership as policy-relevant metadata, evaluate deny-by-default ACL independently, and audit scope selection. Begin with explicit project filters in query contracts; add profile defaults only after role/access ownership exists.

## Capability comparison

### Capabilities article has that pipeline lacks

These are article-reported capabilities absent or unproven in current repository scope:

1. Production-like multi-source ingestion across Slack, wiki/Confluence, code, incidents, and custom databases.
2. Slack Socket Mode event path with deduplication, whole-thread refresh, channel-specific cadence, and real-time updates.
3. LLM thread distillation into query/summary/resolution/system/code-reference artifacts.
4. Burst extraction and burst-level embeddings with rare-token, length, and reaction signals.
5. 3,072-dimensional pgvector embeddings and HNSW.
6. PostgreSQL FTS/GIN plus semantic retrieval, IDF, age decay, and multi-list RRF.
7. Reranker-based top-ten selection and post-ranking neighbor context expansion.
8. Language-aware recursive code chunking and incremental commit synchronization through CocoIndex.
9. Reviewed or self-service source onboarding model for custom databases.
10. Planner/executor fan-out over source-specific retrieval tools.
11. MCP retrieval primitives for agents.
12. Projects that bundle sources and provide default query scope.
13. Reported adoption at more than 15,000 questions/day and use by humans, automations, and agents.

Article does not provide enough operational detail to treat these as production requirements for this project.

### Capabilities pipeline has that article omits or does not establish

These repository capabilities or constraints are not described in article and should not be discarded:

1. Canonical change/ledger concepts with stable object identity, revisions, permissions, and provenance links.
2. Explicit authority boundary: PostgreSQL target authority; raw object storage; indexes derived and rebuildable; model non-authoritative.
3. Transactional outbox/CDC direction and replay/checkpoint semantics in target architecture.
4. Deny-by-default tenant/source ACL contract, immutable Principal/AuthZ ports, tombstones, and revocations.
5. Purge intent, status, evidence, source/document scope, and cross-store verification requirements.
6. Fake-provider production guards, real OIDC/KMS requirements, key lifecycle, and encryption boundaries.
7. Abstention requirement when authorized evidence is insufficient; model output cannot grant access or become source truth.
8. Recovery, backup, RPO/RTO, load, SLO, observability, on-call, and named approval gates.
9. Failure ownership, idempotency, cancellation, timeout, rate-limit, and replayability contracts.
10. Current local/reference evidence boundaries, supported-runtime requirement, and explicit real-data NO-GO.
11. Existing FTS5 lexical search, local raw artifacts, test-manifest provenance, readiness lag checks, and bounded purge/replay reference paths.
12. Phase 1 decision to keep Python semantic policy/contracts and avoid Go rewrite.

Article’s “simple shared table” must therefore become a derived projection behind these controls, not an invitation to flatten authority or security semantics.

## Ranked gaps

Ranking reflects risk to safe pilot, not article feature appeal.

### P0 — blocks pilot or corrupts trust

1. **Production authority and atomic workflow.** Replace SQLite/reference authority with PostgreSQL accepted-state model and durable outbox/relay; prove crash/replay behavior.
2. **Real identity, authorization, and key management.** Replace fake OIDC/KMS; enforce tenant/source isolation and deny-by-default at every query, expansion, answer, and purge boundary.
3. **Verified deletion and purge evidence.** Cover raw bytes, canonical state, FTS/vector projections, caches, backups, and external connector artifacts.
4. **Recovery and operations evidence.** Define and qualify SLO, RPO ≤24h, RTO ≤4h targets, load evidence in supported runtime, alerts, runbook, ownership, and rehearsal.
5. **Ingestion correctness contract.** Approved connector, stable identity, cursor/resume, permissions, incomplete snapshots, retries, and deletion signals.

### P1 — required for useful production-shaped retrieval

6. **Postgres FTS plus pgvector projection.** Build rebuildable projections with model/index versioning, ACL filtering, and freshness.
7. **Canonical document/chunk projection.** Preserve source lineage, offsets, revisions, metadata, citations, and context relationships.
8. **Hybrid retrieval baseline.** FTS/vector candidate generation, deterministic fusion, dedupe, diversity cap, and evidence packet.
9. **Source-aware ingestion/distillation.** Start with approved text connector; add optional summaries only with lineage and abstention-safe failure behavior.
10. **Query contract and evidence schema.** Typed retrieval results with scores, source hints, freshness, citations, and policy decision evidence.
11. **Observability and evaluation.** Measure recall, groundedness, citation correctness, ACL leakage, freshness, latency, storage, and purge completeness.

### P2 — valuable after hardening

12. Slack real-time Socket Mode and whole-thread reingestion.
13. Burst embeddings and configurable rare-token/reaction filters.
14. Code semantic indexing with language-aware recursive chunks and incremental sync.
15. RRF across more than two retrievers, reranking, and bounded context expansion.
16. Projects and default query scope, with independent ACL checks.
17. MCP primitive tools and planner/executor fan-out.

### P3 — scale or optimization work

18. Six-list retrieval parity and source-specific weighting.
19. Large-repository onboarding, path allowlists/denylists, and CocoIndex-like sync.
20. `who_knows`, recent-PR retrieval, subsystem summaries, and richer agent workflows.
21. OpenSearch migration or hybrid index split when measured trigger is met.

## MVE decisions: relevant versus overkill

### Relevant for initial MVE

- Postgres authority and transactional accepted-state model.
- Postgres FTS/GIN for exact lexical retrieval.
- pgvector for one semantic projection, with HNSW only after benchmark.
- One approved text connector behind stable contracts.
- Canonical document/chunk projection with provenance, ACL references, revision, and citation offsets.
- Two-way hybrid baseline: FTS plus vector, deterministic merge, dedupe, freshness, and source caps.
- Explicit abstention, citations, purge, replay, and evidence records.
- Real OIDC/KMS, deny-by-default authorization, observability, recovery, and gate evidence.
- Project filter as an explicit query parameter if product owner defines semantics; no automatic profile default yet.

### Relevant later, not MVE blocker

- Slack Socket Mode and thread distillation.
- Burst embeddings.
- Code embeddings, recursive language-aware chunking, and incremental sync.
- Additional retrievers, RRF with six lists, LLM reranker, and neighbor expansion.
- MCP primitive tools, planner/executor, agents, `who_knows`, and recent PRs.

### Overkill or unsafe for initial MVE

- Reproducing Cerebras’s six-list topology before measuring two-list baseline.
- 3,072 dimensions by imitation; choose model/dimension by evaluation and cost.
- Arbitrary unreviewed connector/plugin execution.
- Generic unrestricted agent/tool access.
- Graph retrieval merely because article diagrams show graph-like signals; current MVE has no approved graph authority or scope.
- OpenSearch before scale/latency/operational trigger.
- LLM-generated summaries as authority or sole citation.
- Broad multi-source onboarding while fake identity/KMS, SQLite authority, incomplete purge, and recovery gaps remain.

## Phase 0–5 changes

Phase names below are this evaluation’s bounded implementation sequence. They refine existing Phase 1 terminology; they do not change existing docs.

### Phase 0 — decision and safety baseline

- Record article provenance and claim/recommendation separation.
- Resolve initial search target to pgvector + PostgreSQL FTS; record OpenSearch trigger.
- Freeze text-first scope and current NO-GO boundary.
- Define owners for retention, purge, roles, SLO, RPO, and RTO.
- Establish evaluation corpus and leakage/groundedness/citation metrics before retrieval tuning.

Exit: written ADRs, owners, thresholds, threat model, and no real data.

### Phase 1 — contracts and authority hardening

- Keep Python adapter/orchestrator and stable contracts.
- Replace fake ACL/OIDC and fake KMS path with production integration plan and test boundary.
- Define canonical document, chunk, projection, evidence, citation, and deletion contracts.
- Move accepted knowledge authority toward PostgreSQL with transactional outbox/relay.
- Preserve source identity, revisions, permissions, provenance, and purge evidence.

Exit: contract tests for deny, provenance, idempotency, replay, purge, and failure ownership; still NO-GO until production evidence.

### Phase 2 — ingestion and document projections

- Integrate one approved text connector through Nango-backed boundary.
- Add raw-byte/object-storage contract and canonicalizer for UTF-8, Markdown, and CSV.
- Produce rebuildable document/chunk and PostgreSQL FTS projections.
- Add optional, lineage-preserving distillation interface; no required LLM dependency.
- Add freshness, watermark, deletion, and incomplete-snapshot evidence.

Exit: ING evidence and source-scoped purge/replay pass for synthetic data.

### Phase 3 — semantic and hybrid retrieval

- Add pgvector projection and model/version metadata.
- Benchmark HNSW against exact/alternative configuration; capture recall, filtered behavior, build cost, and latency.
- Implement FTS + vector candidate retrieval, deterministic RRF/fusion module, dedupe, diversity cap, and typed evidence packet.
- Add citation offsets and authorized context assembly.
- Defer reranker and burst until baseline metrics justify them.

Exit: ANS evidence for relevance, authorization, citations, abstention, freshness, and latency.

### Phase 4 — source-specific quality and scope

- Add Slack adapter only after identity, permissions, cursors, reingest, and purge contracts pass.
- Add thread distillation and configurable bursts as derived artifacts.
- Add code indexing only with path policy, commit lineage, incremental synchronization, and ripgrep fallback.
- Add project filters and source-specific retrieval weights with independent ACL evaluation.
- Add reranking and bounded context expansion only from measured error cases.

Exit: source-specific evaluation and PUR/OPS evidence; no automatic production approval.

### Phase 5 — consumers and scale

- Add MCP primitive tools with narrow typed schemas and policy enforcement.
- Add bounded planner/executor/synthesis path for web UI and agent clients.
- Add default project profile only after role/access ownership and audit behavior are approved.
- Add additional retrievers, six-list fusion, `who_knows`, recent PRs, and subsystem index when product value is demonstrated.
- Reassess OpenSearch only when trigger metrics are recorded; migrate via shadow, comparison, cutover, and rollback.

Exit: consumer contract, audit, capacity, recovery, and production approval evidence. NO-GO remains default.

## Bounded coding tickets

Tickets are intentionally small. Each has one bounded outcome, explicit non-goal, and acceptance evidence. None authorizes real-data use or bypasses gates.

| ID | Phase | Ticket | Acceptance evidence | Explicit non-goal |
|---|---|---|---|---|
| **KB-001** | 0 | Add article-evaluation ADR and claim/recommendation labels. | ADR links canonical URL, authors/date, access date, confidence, and decision. | No implementation change. |
| **KB-002** | 0 | Record pgvector + PostgreSQL FTS initial search decision and OpenSearch trigger. | Decision states authority, derived indexes, benchmark/scale triggers, rollback expectation. | No OpenSearch deployment. |
| **KB-003** | 0 | Define retrieval evaluation fixture and metrics schema. | Fixture records query, authorized sources, expected evidence, citation, ACL, freshness, latency fields. | No claim of production quality. |
| **KB-004** | 1 | Add typed `DocumentProjection` and `ChunkProjection` contracts. | Contract tests cover identity, revision, source, offsets, metadata, model/index version, and lineage. | No connector or embedding provider. |
| **KB-005** | 1 | Add typed `EvidenceRow`, citation, and abstention contracts. | Tests reject missing provenance/citation fields and represent insufficient evidence explicitly. | No LLM answer generation. |
| **KB-006** | 1 | Add PostgreSQL authority/outbox repository boundary behind existing Python contracts. | Atomic accepted-state + outbox tests; replay and idempotency evidence recorded. | No production cutover before authority gate. |
| **KB-007** | 1 | Add authorization checks to projection, retrieval, expansion, answer, and purge interfaces. | Deny-by-default tenant/source tests; unauthorized rows never consume result slots. | Does not replace real OIDC/KMS integration. |
| **KB-008** | 1 | Add projection deletion and purge-evidence ledger. | Synthetic purge covers raw, canonical, FTS/vector projections and records unverifiable states. | No claim over external systems not integrated. |
| **KB-009** | 2 | Implement one approved text connector adapter with cursor/revision/delete contract. | Connector tests cover retries, rate limits, resume, incomplete snapshot, and deletion signal. | No Slack or arbitrary plugin ingestion. |
| **KB-010** | 2 | Implement canonical text-to-document/chunk projection for UTF-8, Markdown, and CSV. | Stable IDs, offsets, provenance, deterministic chunking, and replay tests pass. | No PDF/OCR/image/attachment support. |
| **KB-011** | 2 | Implement PostgreSQL FTS projection and query adapter. | Exact-token, tenant-filter, tombstone, freshness, and rebuild tests pass. | No claim that FTS alone solves semantic retrieval. |
| **KB-012** | 3 | Add versioned embedding/model port and pgvector projection. | Dimension/model/index metadata, deterministic upsert, rebuild, and deletion tests pass. | No mandated 3,072-dimensional model. |
| **KB-013** | 3 | Add pgvector HNSW benchmark harness. | Recall, filtered recall, build cost, memory, and latency report on fixture corpus. | No production capacity certification. |
| **KB-014** | 3 | Add deterministic FTS + vector fusion module. | Named weights, `K`, rank inputs, dedupe, source cap, and intermediate evidence are testable. | No six-list parity or LLM reranker. |
| **KB-015** | 3 | Add authorized context expansion with bounded neighbors. | Expansion rechecks ACL/tombstone, caps tokens/neighbors, and cites matched versus expanded text. | No automatic expansion of arbitrary sources. |
| **KB-016** | 4 | Add optional threaded-source distillation artifact interface. | Full source lineage, prompt/model version, failure isolation, and source citation tests pass. | Distillation cannot become authority or required ingest path. |
| **KB-017** | 4 | Add configurable burst extraction/filtering. | IDF/length/reaction signals, thresholds, lineage, duplicate suppression, and purge tests pass. | No default production enablement before recall/storage review. |
| **KB-018** | 4 | Add project scope to query contract and audit record. | Explicit project/source scope, independent ACL evaluation, and audit tests pass. | No profile default or access grant. |
| **KB-019** | 4 | Add code projection contract with path policy and commit lineage. | File/function chunks, allow/deny paths, incremental changed-chunk sync, and ripgrep fallback are tested. | No repository onboarding or CocoIndex adoption. |
| **KB-020** | 5 | Add narrow MCP retrieval tools. | Typed `search`, source search, and evidence output schemas enforce auth, limits, citations, and errors. | No unrestricted answer/edit tool or planner requirement. |
| **KB-021** | 5 | Add bounded planner/executor/synthesis orchestration. | Planner scope is constrained; executor parallelism/timeouts/partial results are tested; synthesis cites or abstains. | No production agent access, default projects, or OpenSearch migration. |

## Verification and release constraints

Every ticket requires unit/contract tests plus evidence appropriate to its phase. Retrieval tickets require ACL-leakage, deletion, provenance, freshness, and deterministic replay tests. Consumer tickets require tool authorization, limits, timeout, audit, and abstention tests. Derived indexes must be rebuildable from authoritative state.

Production remains **NO-GO** until existing gates pass:

- **SEC:** real OIDC, authorization, tenant/source isolation, real KMS, key lifecycle, and review;
- **ING:** approved connector, ingestion correctness, permissions, cursor/resume, and deletion;
- **ANS:** grounded answers, complete citations, authorized evidence, and explicit abstention;
- **PUR:** retention policy, deletion across artifacts, verified purge, and evidence;
- **OPS:** recovery rehearsal, alerts, runbook, load/SLO, RPO/RTO, ownership, and approvals.

Current baseline acceptance targets remain ingest ≥100 records/s, search p95 ≤100 ms, RPO ≤24h, and RTO ≤4h. They require a supported-runtime qualifying run; article results do not satisfy them. Keep real input synthetic until pilot owner approves exit gates.

## Source links and notes

### Primary source

- [Cerebras — How We Built Our Knowledge Base](https://www.cerebras.ai/blog/how-we-built-our-knowledge-base) — canonical URL; article dated 2026-07-15; authors Isaac Tai, Daniel Kim, and Mike Gao.

### Article references

- [HNSW paper](https://arxiv.org/abs/1603.09320)
- [Anthropic — Contextual Retrieval](https://www.anthropic.com/news/contextual-retrieval)
- [RRF paper](https://dl.acm.org/doi/10.1145/956863.956972)
- [Search-o1](https://arxiv.org/abs/2501.05366)
- [Anthropic — Code Execution with MCP](https://www.anthropic.com/engineering/code-execution-with-mcp)
- [Lost in the Middle](https://arxiv.org/abs/2307.03172)
- [Anthropic — XML tags](https://docs.anthropic.com/en/docs/build-with-claude/prompt-engineering/use-xml-tags)
- [Slack Engineering — Slack AI](https://slack.engineering/how-slack-ai-processes-billions-of-messages/)
- [Improving Agents — nested data format](https://www.improvingagents.com/blog/best-nested-data-format/)
- [Cursor — semantic search](https://cursor.com/blog/semsearch)

### Repository sources inspected

- [`docs/phase1-product-brief.md`](phase1-product-brief.md) — text-first MVE, NO-GO gates, deferred vectors/MCP, migration order.
- [`docs/phase1-architecture-decision.md`](phase1-architecture-decision.md) — authority boundary, adapters, outbox/CDC, production gates, prior unresolved OpenSearch/pgvector conflict.
- [`docs/phase1-library-research.md`](phase1-library-research.md) — pgvector default, PostgreSQL authority, connector/workflow/telemetry recommendations.
- [`docs/architecture.md`](architecture.md) — checked-in SQLite/FTS5 reference behavior and production blockers.
- [`docs/mvp-plan.md`](mvp-plan.md) — hardening sequence and pilot acceptance.
- [`BII.md`](../BII.md) — canonical object versus document/relational/vector projections.

### Recovery and unresolved detail note

Direct fetch of the canonical Cerebras URL returned an HTTP 500 during this evaluation. Article text and metadata were recovered from a dated public capture of the same canonical URL, downloaded 2026-07-20, and cross-checked against the canonical link and article references. This preserves substantive article content, but not original page layout, diagrams as executable specifications, code, benchmark data, exact connector implementation, exact six-list composition, exact fusion weights beyond `K=60` and default weight 1.0, reranker model identity, prompt text, infrastructure topology, security implementation details, retention/purge behavior, or operational SLOs. Those details are unrecoverable from available source material and are not invented here.

## Diff check

Allowed write scope contains four Markdown files: `docs/phase1-product-brief.md`, `docs/phase1-library-research.md`, `docs/phase1-architecture-decision.md`, and `docs/article-evaluation-cerebras-knowledge-base.md`. Code and tests were not modified. All four files were reread after update for allowed paths, status visuals, research-record standards, source links, NO-GO constraints, and pgvector/OpenSearch decision consistency.
