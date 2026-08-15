# Phase 2 Security Review

```text
+--------------------------------------------------------------+
| STATUS: REVIEW COMPLETE                            PROD: NO-GO|
| DONE: threat model; policy decision; search review; exits      |
| OPEN: real identity/KMS; authority; purge; evidence            |
| BLOCKERS: P0/P1 findings below remain release-blocking         |
| NEXT: remediate, test, independently validate, then re-review  |
+--------------------------------------------------------------+
```

## Provenance and preservation

| Field | Value |
|---|---|
| Source agent | Security Engineer |
| Review date | 2026-08-15 |
| Owner | Security Engineering; accountable individual to be assigned |
| Validation owner | Parent / Security Engineering owner to be assigned |
| Review scope | Phase 2 security review of ingestion, authority, projections, query/answer, purge, deployment, and operations |
| Source record | Completed Security Engineer output in parent context; findings copied into this record |
| Related Phase 1 records | [`phase1-product-brief.md`](phase1-product-brief.md), [`phase1-architecture-decision.md`](phase1-architecture-decision.md), [`phase1-library-research.md`](phase1-library-research.md), [`article-evaluation-cerebras-knowledge-base.md`](article-evaluation-cerebras-knowledge-base.md) |

This record preserves full substantive findings, not an executive summary. Findings,
recommendations, repository evidence, and editorial organization remain distinct.
Missing source transcript details are not invented. Any item marked unresolved remains
unresolved. Completion of a reference test does not equal production security approval.

## Security decision

**NO-GO.** System cannot process confidential, customer, regulated, email, attachment,
or credential data. Production approval requires real identity and key-management
boundaries, authoritative persistence, complete authorization enforcement, verified
cross-store purge, and security evidence owned and reviewed by named people.

Current direction remains PostgreSQL authority with **pgvector plus PostgreSQL full-text
search** as initial retrieval. OpenSearch remains deferred until a measured scale,
latency, operational-isolation, or retrieval-feature trigger is met. This is an initial
retrieval decision, not a security waiver or production approval.

## Assets, trust boundaries, and threat zones

### Assets

- Customer and tenant documents, raw bytes, extracted text, chunks, embeddings, FTS data,
  metadata, ACLs, tombstones, retention state, and purge evidence.
- Credentials, OAuth tokens, OIDC tokens, JWKS material, KMS keys, encryption context,
  workflow state, cursors, checkpoints, audit records, and operational telemetry.
- PostgreSQL accepted knowledge state and transactional outbox. PostgreSQL is authority.
  Object storage owns raw bytes. Indexes are derived and rebuildable. Model output is not
  authority.

### Threat zones

| Zone | Components / trust boundary | Security consequence |
|---|---|---|
| Z1: external identity and callers | Browser/API caller, OIDC issuer, JWKS, OAuth providers | Token spoofing, issuer/audience confusion, replay, missing tenant binding |
| Z2: connector ingress | Nango or approved connector, source APIs, cursors, webhook/sync input | Credential theft, malicious source content, forged deletion, cursor tampering |
| Z3: authority and workflow | PostgreSQL, outbox/CDC relay, Temporal workflows, audit ledger | Unauthorized state transition, replay/gap corruption, non-repudiation failure |
| Z4: raw storage and keys | S3-compatible object store, KMS, envelopes, backups | Plaintext disclosure, wrong-key access, incomplete deletion, backup retention leak |
| Z5: parsing and projection | Parser, chunker, embeddings, pgvector, PostgreSQL FTS, optional OpenSearch | Prompt/content injection, cross-tenant projection, index poisoning, stale ACLs |
| Z6: query and answer | Policy layer, retrievers, planner, Ollama/model port, citations | ACL bypass, context leakage, unsafe tool behavior, unsupported answer claims |
| Z7: operations and delivery | CI/CD, deployment, metrics, logs, traces, admin/on-call paths | Secret leakage, supply-chain compromise, privilege escalation, outage/DoS |

### Protected flows

1. **Ingestion:** authenticated connector reads source changes; stable source identity and
   cursor are recorded; raw bytes enter encrypted object storage; accepted metadata enters
   PostgreSQL; outbox event is committed with accepted state. Connector must not become
   authority, and Nango cache must not be treated as archive.
2. **Projection:** relay consumes durable events; parser extracts content and metadata;
   chunker creates stable source/document-provenanced chunks; embeddings and FTS are
   derived projections. Projection failure must not rewrite authority. Replay rebuilds
   projections idempotently.
3. **Query:** authenticated principal is mapped to tenant, role, and source scope;
   deny-by-default policy runs before retrieval; ACL/tombstone/revocation filters run before
   result limits and context expansion; only authorized context reaches model; response
   carries provenance/citations or abstains.
4. **Purge:** retention policy creates purge intent; workflow deletes raw bytes, accepted
   state, projections, caches, backups subject to policy, and audit-linked evidence; each
   store reports completion; missing or unverifiable deletion fails closed.
5. **Administration and deployment:** operators authenticate through production identity;
   least-privilege roles separate deploy, key, data, and audit duties; secrets stay outside
   code, images, client bundles, and logs; rollback cannot resurrect revoked data.

## STRIDE threat model

| Zone / flow | S | T | R | I | D | E |
|---|---|---|---|---|---|---|
| Identity and API | Fake issuer/token, bearer replay | Claims or request mutation | Missing immutable request/audit identity | Error, token, or cross-tenant response leakage | Unbounded requests, login abuse | Missing endpoint authz or role escalation |
| Connector ingress | Forged connector/OAuth identity | Cursor, source ID, deletion signal mutation | No source event/cursor evidence | Token/content exposure in logs | Source/API rate exhaustion, oversized files | Connector granted broader tenant scope |
| PostgreSQL authority/outbox | Rogue DB/workflow principal | Non-atomic ledger/outbox or replay gap | Mutable audit trail, absent actor/correlation ID | Broad DB reads, backup exposure | Lock/contention, queue growth | DB role or workflow can bypass policy |
| Object store/KMS/backups | Wrong workload/key identity | Envelope/context or object metadata tamper | No deletion/key-use evidence | Plaintext, wrong tenant key, retained backup | Storage exhaustion or KMS outage | Key-admin/data-admin privilege collapse |
| Parser/chunker/projections | Untrusted worker identity | Poisoned chunks, embeddings, FTS/OpenSearch docs | No model/index/version provenance | ACL omitted from derived result | Parser bombs, embedding/index exhaustion | Worker writes authority or other tenant index |
| Query/planner/model | Spoofed principal or tool | Prompt/context/citation manipulation | Unlogged planner/tool decisions | Unauthorized context or model telemetry | Expensive queries, fan-out, token exhaustion | Model/tool output grants access |
| Purge flow | Forged purge request | Partial deletion, tombstone reversal | No evidence of each store | Residual data in index/cache/backup | Retry storm or unbounded purge | Operator can purge outside scope |
| Delivery/operations | Stolen CI/operator identity | Image/config/secret tamper | Weak release/change records | Logs/traces reveal data/secrets | Bad deploy, alert storm, dependency outage | CI or on-call role becomes data admin |

## Findings by severity

Severity follows P0 customer/data emergency, P1 release-blocking security risk, and P2
important gap that must be tracked and closed before the applicable production scope.

### P0 blockers

| ID | Finding | Required control / evidence |
|---|---|---|
| SEC-P0-1 | No production-authenticated identity and tenant boundary. Offline/fake OIDC/JWKS validation and process-local claims do not prove issuer trust, JWKS rotation, authenticated user identity, tenant isolation, or source-enforced ACL. | Real OIDC/JWKS integration; issuer/audience/expiry/signature validation; key rotation and revocation behavior; tenant/source authorization tests; negative cross-tenant tests; production composition rejects fake providers. |
| SEC-P0-2 | PostgreSQL is not yet production authority. Local SQLite ledger/outbox/reference paths do not prove atomic coordination of accepted state, raw metadata, projection trigger, audit, and recovery. | Production PostgreSQL transaction and outbox design; crash/failure injection; replay/gap evidence; role separation; immutable correlation/audit evidence; restore and consistency validation. |
| SEC-P0-3 | Encryption/key boundary is fake or incomplete. Fake KMS envelopes and encrypted raw persistence tests do not prove real KMS calls, credential handling, rotation, retirement, decryption reads, or canonical ledger ciphertext migration. | Real KMS envelope encryption; least-privilege key roles; rotation/retirement/erasure tests; encrypted-at-rest and in-transit evidence; successful persisted-artifact decrypt path; no plaintext fallback; canonical ledger migration. |
| SEC-P0-4 | Complete deletion is not proven across raw data, authority, derived indexes, caches, backups, and retention boundaries. | Named retention policy/owner; idempotent purge workflow; per-store deletion receipts; tombstone and revocation ordering; backup/replica treatment; negative retrieval tests; restore-after-purge test; unresolved deletion blocks completion. |

### P1 blockers

| ID | Finding | Required control / evidence |
|---|---|---|
| SEC-P1-1 | Authorization can be bypassed if filters run after ranking, limiting, or context expansion. | Enforce deny-by-default policy and tenant/source ACL, tombstone, and revocation filters before limits and expansion; test direct API, retriever, planner, cache, and model paths. |
| SEC-P1-2 | Derived search state can become stale or cross-tenant. | PostgreSQL remains authority; projection metadata carries tenant/source/document, ACL version, model/index version, and freshness; rebuild/replay and stale-revocation tests; no index result grants access. |
| SEC-P1-3 | Untrusted document content reaches parser, planner, or model as instructions. | Treat content as data; isolate parser/model workers; constrain planner/tools; validate citations against authorized evidence; deterministic abstention when evidence is insufficient; injection tests. |
| SEC-P1-4 | Connector credentials, tokens, source content, and sensitive payloads may leak through logs, traces, errors, caches, or client responses. | Secret manager/KMS integration; redaction tests; structured allow-listed DTOs; retention/access controls for telemetry; no credentials or raw content in client or logs. |
| SEC-P1-5 | Resource exhaustion is not production-qualified. Local parser limits do not establish endpoint, source, tenant, storage, query, embedding, or model quotas. | Per-user/IP/tenant/endpoint rate limits; bounded file/parser/token/query/fan-out limits; timeout, retry, backpressure, circuit breaker, and bulkhead tests; abuse monitoring. |
| SEC-P1-6 | Rollback or replay can resurrect revoked content or reintroduce unauthorized projections. | Versioned policy/tombstone state; purge-aware replay; shadow comparison; bounded cutover; rollback test proving revoked data remains absent. |

### P2 blockers

| ID | Finding | Required control / evidence |
|---|---|---|
| SEC-P2-1 | Role definitions, grants, key-admin/data-admin separation, and break-glass process remain incomplete. | Access matrix, least-privilege grants, periodic review, emergency access audit, owner sign-off. |
| SEC-P2-2 | Security audit evidence lacks complete transformation chain, freshness, formal citations, and tamper-evident retention. | Correlation IDs from source through answer/purge; document/chunk/model/index versions; immutable evidence bundle and retention policy. |
| SEC-P2-3 | Dependency/license/deployment/upgrade confidence is incomplete for parser, connector, workflow, retrieval, identity, and telemetry components. | Maintained inventory, SBOM/scanning, patch SLA, license review, supported deployment model, owner, and rollback plan. |
| SEC-P2-4 | Network segmentation, egress controls, service-to-service authentication, and administrative boundaries are not demonstrated. | Architecture and firewall policy; mTLS/workload identity where required; restricted egress; verified admin-plane separation. |
| SEC-P2-5 | Security monitoring and incident response are not production-ready. | Alerts for authz denials, token/key failures, purge failures, abnormal exports, injection indicators, and privilege changes; runbooks and exercise evidence. |

## Cedar / OPA policy decision

Use **Cedar for runtime authorization** when policy is evaluated at the application
resource/action boundary. Model tenant, source, document, role, and action explicitly;
default deny; pass authenticated principal and resource attributes from trusted adapters;
test both allow and deny paths. Cedar does not authenticate callers, own source truth,
replace Python contract enforcement, or prove purge.

Use **OPA** when policy must integrate across platform controls such as deployment,
admission, infrastructure, network, or organization-wide compliance. OPA is not a reason
to move runtime data authorization out of the semantic application boundary.

**Decision:** Cedar runtime policy plus OPA where platform-wide policy integration is
needed. Python remains responsible for identity mapping, contract enforcement, provenance,
deny-by-default composition, and fail-closed behavior. Do not run both as independent
authorizers without precedence, conflict, timeout, and audit rules. A policy decision
must never grant access based on model output or derived-index presence.

## pgvector and OpenSearch security analysis

### pgvector plus PostgreSQL FTS — initial target

- Keeps vectors and FTS beside PostgreSQL authority, reducing trust boundaries and making
  transactional metadata, ACL state, tombstones, and projection versioning easier to bind.
- Does not automatically provide row-level tenant isolation, safe filtered ANN behavior,
  encryption, or authorization. Enforce policy before query and add defense-in-depth
  database roles/RLS where compatible with the authority design.
- Embeddings can disclose sensitive semantic information. Encrypt storage/backups, limit
  vector access, avoid logging vectors or raw query context, and purge vectors with source
  data. Validate filtered recall and stale-ACL behavior.
- HNSW/index build and filtered-query resource use require benchmark evidence. Model,
  dimension, index version, tenant/source scope, and freshness must be explicit. Article
  claims of 3,072 dimensions are not a requirement.

### OpenSearch — deferred option

- Adds a separate datastore, credentials, network path, ACL projection, backup, purge,
  upgrade, and operational ownership boundary. A copied ACL can be stale or incomplete;
  OpenSearch must never become authority or decide access by itself.
- Security controls require tenant-aware index/document permissions, TLS, service identity,
  encryption, audit logging, snapshot deletion semantics, and query filtering verified
  against aliases, caches, aggregations, and fallback paths.
- Migration must use shadow indexing, authorized-result comparison, freshness and purge
  comparison, bounded cutover, and rollback. Rollback must preserve PostgreSQL authority
  and revoked-data state.

**Trigger:** consider OpenSearch only after measured scale, query latency, operational
isolation, or retrieval-feature limits exceed the PostgreSQL design envelope and security,
purge, backup, and ownership costs are accepted. No OpenSearch deployment is required
for current initial scope.

## Mandatory security exit criteria

- [ ] Named security owner, product owner, operations owner, and data/privacy approver.
- [ ] Real OIDC/JWKS, rotation, issuer/audience, expiry, revocation, and authenticated
  tenant/source isolation evidence.
- [ ] Cedar runtime policy and any OPA platform policy have documented precedence,
  timeout, deny behavior, audit fields, and positive/negative test coverage.
- [ ] Real KMS integration, envelope context binding, rotation, retirement, erasure,
  credential controls, encrypted read path, and canonical ledger migration.
- [ ] PostgreSQL production authority, atomic outbox, role separation, crash/replay/gap
  evidence, and immutable audit trail.
- [ ] Authorization filters occur before retrieval limits and context expansion across
  API, FTS, pgvector, caches, planner, tools, model, and fallback paths.
- [ ] Parser/content injection controls, request/file/query/model limits, rate limiting,
  timeouts, backpressure, and dependency failure controls are tested.
- [ ] Cross-store purge policy, owner, SLA, evidence receipts, backup/replica semantics,
  restore-after-purge test, and fail-closed incomplete deletion behavior.
- [ ] Search decision and trigger recorded; pgvector/FTS security benchmark complete;
  no OpenSearch production claim before its separate review.
- [ ] Secrets, logs, traces, DTOs, client responses, and error paths pass disclosure review.
- [ ] Security monitoring, incident runbooks, dependency inventory/SBOM, patch process,
  deployment controls, and independent review complete.
- [ ] All P0/P1 findings closed with dated evidence. P2 owners and due dates accepted.

```text
SECURITY EXIT
Identity/KMS       [░░░░░░░░░░] BLOCKED
Authority          [░░░░░░░░░░] BLOCKED
Authorization      [░░░░░░░░░░] BLOCKED
Purge              [░░░░░░░░░░] BLOCKED
Search security    [██░░░░░░░░] Direction only
Evidence/review    [░░░░░░░░░░] BLOCKED
PRODUCTION         [░░░░░░░░░░] NO-GO
```

## Recovery limits

This record preserves substantive security findings available in Phase 2 output and
repository evidence. Any source-agent sentence, numeric threshold, diagram, or finding
not represented here is unrecoverable from current workspace context and must not be
reconstructed by inference. Existing reference tests and fake adapters remain evidence
of narrow behavior only; they do not change NO-GO.
