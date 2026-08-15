# Phase 2 SRE Review

```text
+--------------------------------------------------------------+
| STATUS: REVIEW COMPLETE                            PROD: NO-GO|
| DONE: evidence classification; architecture; ops plan         |
| OPEN: supported load; numeric qualification; production ops   |
| BLOCKERS: authority, recovery, observability, owners           |
| NEXT: qualify runtime, rehearse failure, close exit criteria   |
+--------------------------------------------------------------+
```

## Provenance and preservation

| Field | Value |
|---|---|
| Source agent | Senior SRE |
| Review date | 2026-08-15 |
| Owner | SRE / Operations; accountable individual to be assigned |
| Validation owner | Parent / SRE owner to be assigned |
| Review scope | Phase 2 reliability, operability, capacity, recovery, deployment, cost, UX/planner, and exit review |
| Source record | Completed SRE output in parent context; findings copied into this record |
| Related records | [`phase1-product-brief.md`](phase1-product-brief.md), [`phase1-architecture-decision.md`](phase1-architecture-decision.md), [`phase1-library-research.md`](phase1-library-research.md), [`article-evaluation-cerebras-knowledge-base.md`](article-evaluation-cerebras-knowledge-base.md), [`pipeline-progress.md`](pipeline-progress.md), [`pilot-readiness.md`](pilot-readiness.md) |

Full findings are preserved rather than reduced to status. Evidence classification is
explicit: fixture/reference evidence cannot be promoted to production evidence by test
count, green checks, or visual completion. Unresolved ownership and thresholds remain
open. This record preserves **NO-GO**.

## SRE decision and architecture recommendation

**NO-GO.** Current system is local/reference shaped. Do not load confidential, customer,
regulated, email, attachment, or credential data. Production pilot requires supported-
runtime load, numeric SLO/RPO/RTO comparison, production authority, real identity/KMS,
external connector and projection evidence, deployment, observability, runbooks, and
rehearsed recovery with named owners.

Recommended production shape:

- PostgreSQL is authoritative for accepted knowledge state and transactional outbox.
- Object storage owns raw bytes; pgvector plus PostgreSQL FTS are initial rebuildable
  projections. OpenSearch is later, only after measured trigger and separate review.
- Temporal or equivalent durable workflows own retry, timeout, cancellation, idempotency,
  purge, and recovery orchestration.
- Python contracts remain semantic policy, provenance, citation, and thin API boundary;
  commodity connectors, parser, storage, identity, KMS, model, and telemetry stay behind
  adapters.
- OTel instrumentation exports to metrics, logs, and traces; Prometheus/Grafana or
  deployment-managed equivalents provide actionable dashboards and alerts.
- Per-database access remains serialized in current reference scope. No multi-writer
  support claim is made.

## Evidence classification

| Evidence | Classification | What it proves | What it does not prove |
|---|---|---|---|
| Gate 2/3 test artifacts | Demo/reference | Narrow contracts, ACL denial, tombstones, retries, restart/index behavior, launcher/UI smoke | Production authority, identity, scale, recovery, external integrations |
| Gate 4 fixture QA | Fixture-only | Local purge status, checksummed backup bundles, redacted logs, bounded config, health/replay surfaces | Real-data readiness or production operations |
| Gate 5 results | Fixture/reference | 76 tests twice, six scenarios, checksums, SQLite integrity, restore/interruption and injected-failure outcomes | Coverage, production PostgreSQL, external projections, measured RPO/RTO |
| Gate 6 remediation | Synthetic-local/reference | Serialized DB access, stress pass, projection-lag readiness gate, 78 tests twice, compile/Node checks | Multi-writer, production capacity, supported-runtime SLO qualification |
| Nix environment | Reproducible tooling | Python 3.11.11, Node 22.16, SQLite 3.46; check/benchmark/evidence commands available | Production runtime or infrastructure equivalence |
| Baseline measurements | Synthetic-local | Ingest 694.8 records/s, replay 2607 records/s, 20/20 bounded readers; search timing not retained | Capacity claim, latency SLO compliance, multi-writer safety |
| Recovery rehearsal | Reference scope | SQLite integrity, raw-artifact links, pre-backup retrieval, post-backup absence | Disaster recovery, production RPO/RTO, atomic restore |

`.#benchmark` is QA preflight only. Machine-specific timing is not retained as qualifying
evidence. Supported-runtime load and numeric SLO/RPO/RTO comparison remain pending.

## Failure ownership and dependency boundaries

| Boundary | Owner | Failure behavior / required evidence |
|---|---|---|
| Source API / connector | Connector owner | Rate-limit, cursor, token, deletion, and upstream outage handling; no source failure corrupts authority |
| Identity / policy | Security/platform owner | Fail closed on unavailable or ambiguous authorization; audit decision and latency |
| PostgreSQL authority | Data/platform owner | Atomic accepted state + outbox; backups, replication, locks, restore, and corruption response |
| Object storage / KMS | Storage/security owner | Envelope/key failure blocks unsafe reads/writes; retention and purge receipts; restore validation |
| Relay / workflow | Workflow owner | Idempotent retries, bounded attempts, dead letters, replay, cancellation, timeout, and gap quarantine |
| Parser / chunker | Ingestion owner | Size/type/time limits, isolation, poison input handling, provenance, and replay |
| pgvector / FTS projection | Retrieval owner | Lag and failure visible; rebuildable; never authority; ACL/tombstone freshness gates query |
| Optional OpenSearch | Retrieval/platform owner | Separate ACL, TLS, snapshot, purge, capacity, and rollback evidence before adoption |
| Query/planner/model | Application owner | Timeouts, fan-out/token budgets, partial results, deterministic abstention, citations, no access grant |
| API/UI/deployment | Application/platform owner | Readiness, graceful degradation, canary, rollback, rate limits, and status communication |
| Telemetry/on-call | SRE owner | Dashboards, actionable alerts, runbooks, escalation, postmortems, and retention |

Projection failure must not rewrite authority. Query must expose or enforce freshness
expectations. Missing projection is not authorization. Purge failure is operationally
visible and incomplete state cannot be reported complete.

## SLOs and error budgets

Approved baseline targets are acceptance criteria, not qualification evidence:

| SLI | Baseline target | Measurement required |
|---|---:|---|
| Ingest throughput | ≥100 records/s | Supported runtime, defined record shape, sustained window, resource/saturation data |
| Search latency | p95 ≤100 ms | Authorized query mix, warm/cold behavior, projection freshness, error rate |
| Recovery point objective | ≤24 h | Backup/replication schedule and observed worst-case data loss |
| Recovery time objective | ≤4 h | Restore from declared failure, including validation and service recovery |

Define service availability, ingest success, projection freshness, authorized-search
latency, answer/error rate, purge completion, and recovery SLIs. Use a declared 30-day
rolling or calendar-month window. Error budget is `100% - SLO`; track burn rate and stop
deploys or trigger review when budget is exhausted. Use fast-burn alerting at 5x in 1h and
slow-burn alerting at 2x in 6h, with thresholds calibrated to traffic and impact.

SLO record must include good/bad event definitions, exclusions, sampling, tenant scope,
dashboard query, owner, review cadence, and dependency attribution. No numeric SLO is
qualified until supported-runtime evidence compares measurements to target.

## RPO, RTO, purge SLAs, and recovery

- **RPO ≤24h:** declare backup/replication interval, transaction durability, lag monitor,
  maximum accepted loss, and evidence timestamp. Reference SQLite rehearsal does not prove
  this target.
- **RTO ≤4h:** include detection, declaration, restore, key availability, schema/index
  rebuild, projection catch-up, authorization validation, smoke test, and traffic return.
- **Purge SLA:** Phase 2 requires named retention classes, policy owner, completion target
  per store, evidence retention, backup/replica treatment, and exception/escalation path.
  No purge SLA is accepted until cross-adapter deletion and restore-after-purge behavior
  are tested.
- Backup must be consistent with PostgreSQL authority and object-store references. Validate
  checksums, integrity, key access, catalog/schema compatibility, and dependency versions.
- Restore must be rehearsed from recoverable artifacts, not merely copied locally. Inject
  interruption and dependency failure; record elapsed time, data loss, operator steps,
  failed artifacts, and final verification.
- Purge workflow must be resumable and idempotent. A restore or replay must not resurrect
  tombstoned or revoked content.

## Capacity and load plan

1. Define workload model: tenants, source count, record size, ingest burst/steady rate,
   query mix, concurrent readers, planner fan-out, embedding rate, purge rate, and growth.
2. Run inside pinned supported environment, not only local benchmark app. Record software
   versions, hardware, topology, dataset, warm-up, duration, concurrency, percentile
   latency, error rate, throughput, CPU, memory, disk, I/O, network, DB locks, queue lag,
   projection lag, and cost.
3. Test steady state, burst, dependency slowdown/outage, retry storm, large files,
   backfill/replay, purge load, backup window, and mixed read/write behavior.
4. Establish scaling triggers, safe utilization ceiling, queue/backpressure limits,
   database connection limits, index build budget, storage growth, and six-month forecast.
5. Repeat after schema/index/model changes. Preserve raw result artifacts and compare to
   SLO/error-budget targets. Do not claim multi-writer support while access is serialized.

## Backup, restore, and failure plan

- Protect PostgreSQL authority, object bytes, keys/configuration, workflow state, policy,
  projection metadata, and audit evidence with explicit retention and ownership.
- Test backup creation during writes, checksum/integrity, encryption/key rotation, partial
  failure, interrupted restore, incompatible version, missing object, and missing key.
- Restore authority first; validate outbox/checkpoints; restore raw references; rebuild or
  validate projections; enforce tombstones and ACLs before serving traffic.
- Keep pre- and post-restore authorization, citation, freshness, and purge checks.
- Record run ID, operator, timestamps, source backup IDs, data loss, elapsed time, checks,
  failures, remediation, and sign-off. Evidence must be independently reviewable.

## Deployment, cutover, and rollback

- Package supported runtime and configuration; separate secrets; pin dependencies; scan
  image/SBOM; require change review and owner.
- Use shadow mode before cutover. Compare authorization decisions, provenance, retrieval,
  freshness, purge, latency, errors, and resource use.
- Deploy by bounded capability with canary, feature flags, health/readiness gates, freeze
  windows, and explicit abort thresholds. Liveness means process alive; readiness means
  dependencies, authority, policy, and projection freshness permit traffic.
- Roll back application/projection adapters without changing PostgreSQL authority. Preserve
  tombstones and policy versions; never restore revoked data through rollback.
- Rollback runbook must name decision maker, command/action, data compatibility check,
  traffic drain, verification, communication, and post-rollback reconciliation.
- Cutover is not production-ready until SEC, ING, ANS, PUR, and OPS gates pass.

## Observability specification

- **Logs:** structured JSON; consistent levels; correlation/request/tenant-safe IDs; redact
  tokens, keys, raw content, prompts, and sensitive claims; define access and retention.
- **Metrics:** RED for API/workflows (rate, errors, duration); USE for infrastructure
  (utilization, saturation, errors); ingest rate, queue age, retry/dead-letter count,
  projection lag, freshness, purge age/failures, backup age, restore duration, authz
  denials, KMS/OIDC failures, search latency, answer abstention, and cost signals.
- **Traces:** source-to-authority-to-projection-to-query-to-answer and purge spans; sample
  safely; prevent sensitive payload capture.
- **Dashboards:** answer “is it working?” in five seconds for API, ingestion, projection,
  authority, storage/KMS, purge, recovery, and dependency health.
- **Alerts:** actionable, deduplicated, severity mapped, with owner and runbook. Alert on
  availability/error budget burn, queue/lag, stale authorization projection, backup age,
  purge failure, restore test failure, auth/key errors, saturation, and abnormal export.

## Runbooks and on-call

Required runbooks: API outage, database unavailable/locked, connector outage or token
failure, relay backlog/dead letters, parser poison input, projection lag/index failure,
OIDC/JWKS failure, KMS failure, purge failure, backup failure, restore/disaster recovery,
high latency/resource exhaustion, suspected data disclosure, and rollback.

Incident flow: declare → notify → investigate → mitigate → resolve → postmortem. P0
customer outage/data loss responds within 5 minutes; P1 partial outage/degradation within
15 minutes; P2 non-critical issue within one business day. P0 status updates and executive
summary are required. Postmortems are blameless, include timeline/five whys, owners and
due dates, and receive follow-up review within one week.

Use weekly primary/secondary rotation, documented handoff, escalation to engineering
manager/director, shadowing before primary duty, runbook drills, and game days. Validate
that every page reached on-call, every runbook worked, and every alert was actionable.

## Cost and ownership

Track cost by service, tenant class, and workload: PostgreSQL compute/storage/IOPS,
object storage and retention, KMS operations, workflow/connector calls, embedding/model
compute, telemetry ingestion/retention, backups, egress, and operator time. Right-size,
remove waste, and forecast six months. Do not choose OpenSearch merely for feature appeal;
include second datastore, replicas, snapshots, ACL/purge operations, and on-call cost.

Each component needs owner, budget, scaling trigger, support window, upgrade path, and
decommission plan. Unowned reliability or security controls are blockers.

## UX and planner decisions

- Default answer behavior is deterministic abstention. Generated answers require explicit
  local/reference model opt-in and citations; this does not authorize production data.
- Planner scope is bounded. Enforce per-request timeout, tool allow-list, parallelism,
  token/context budget, retry policy, and partial-result behavior.
- Authorization occurs before planner context expansion and tool execution. Planner or
  model output cannot grant access, select an unauthorized source, or become authority.
- Surface freshness, partial results, citation/provenance, and abstention clearly. Do not
  present stale or unauthorized projection results as complete answers.
- Separate UX failure states: unavailable, stale, denied, insufficient evidence, and
  partial response. Preserve safe failure over plausible but unsupported output.

## Blockers

1. No production-authoritative atomic workflow coordinating raw, canonical, projection, and audit effects.
2. Real OIDC/KMS, authenticated tenant/source boundaries, encrypted read path, and ledger ciphertext migration absent.
3. Cross-adapter purge, backup/restore, measured RPO/RTO, and real-data rehearsal absent.
4. Supported-runtime load evidence and numeric SLO comparison absent; synthetic benchmark is not qualification.
5. Production deployment, observability, alerting, runbooks, on-call, and incident exercises absent.
6. Accepted external connectors and production projection integrations remain unproven; Nango remains experiment-only.
7. Serialized per-database access is validated; no multi-writer claim or production-scale convergence evidence exists.
8. Coverage report unavailable; test count cannot substitute for coverage or operational evidence.
9. Retention classes, purge owner/SLAs, role owners, and numeric threshold owners are not fully assigned.

## Mandatory SRE phase-exit criteria

- [ ] Named owners for authority, identity/KMS, connectors, projections, purge, SLOs,
  recovery, deployment, observability, and on-call.
- [ ] Production architecture and supported runtime deployed in representative topology.
- [ ] Supported-runtime load test meets ingest ≥100 records/s and search p95 ≤100 ms for
  declared workload, with errors, saturation, and projection freshness recorded.
- [ ] SLO definitions, 30-day/calendar window, error budgets, burn alerts, and deploy-stop
  policy approved.
- [ ] RPO ≤24h and RTO ≤4h demonstrated in timed restore/recovery rehearsal with evidence.
- [ ] Purge policy, retention classes, per-store SLAs, backup/replica semantics, and
  restore-after-purge verification approved.
- [ ] Backup/restore, crash, interruption, dependency outage, retry storm, lag, and rollback
  game days pass with dated artifacts.
- [ ] Dashboards answer health in five seconds; alerts are actionable and linked to runbooks.
- [ ] P0/P1 incident process, escalation, status communication, on-call rotation,
  shadowing, training, and postmortem process exercised.
- [ ] Deployment canary, readiness, feature flag, freeze, rollback, and compatibility
  controls pass; rollback cannot resurrect revoked data.
- [ ] Cost model, six-month forecast, budgets, scaling triggers, and component owners exist.
- [ ] UX/planner limits, abstention, citations, freshness, partial-result, and safe-failure
  behaviors pass acceptance tests.
- [ ] Security exit criteria pass; required product/operations/security approvals recorded.

```text
SRE EXIT
Architecture       [██░░░░░░░░] Recommendation only
Supported load     [░░░░░░░░░░] BLOCKED
SLO/error budget   [░░░░░░░░░░] BLOCKED
RPO/RTO            [░░░░░░░░░░] BLOCKED
Purge SLA          [░░░░░░░░░░] BLOCKED
Backup/restore     [██░░░░░░░░] Reference only
Deploy/rollback    [░░░░░░░░░░] BLOCKED
Observability      [░░░░░░░░░░] BLOCKED
On-call/runbooks   [░░░░░░░░░░] BLOCKED
PRODUCTION         [░░░░░░░░░░] NO-GO
```

## Recovery limits

This record preserves SRE evidence classifications, recommendations, blockers, targets,
operational controls, and exit criteria available in Phase 2 output and repository
evidence. Any source-agent detail not represented here is unrecoverable from current
workspace context and must not be inferred. Local green tests, synthetic measurements,
Nix reproducibility, and remediation visuals remain reference evidence; they do not alter
the production NO-GO decision.
