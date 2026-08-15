# Phase 2 UX Design Review

```text
+------------------------------------------------------------------+
| STATUS: UX FINDINGS COMPLETE                           PROD: NO-GO|
| DONE: user model; core flows; failure states; MVE boundary        |
| OPEN: production identity; live freshness; purge evidence; owners |
| WARNING: completion visuals overstate readiness                    |
| NEXT: implement UX gates, then validate with production evidence  |
+------------------------------------------------------------------+
```

## Provenance

| Field | Value |
|---|---|
| Source agent | UX designer |
| Phase | Phase 2 |
| Review date | 2026-08-15 |
| Validation owner | Parent validation owner |
| Review scope | UX, information architecture, user roles, onboarding, search, answers, citations, freshness, purge, recovery, accessibility, and Phase 3 acceptance |
| Source record | Complete UX-design agent findings in parent context; findings preserved here rather than summarized |
| Production decision | **NO-GO** |

This record preserves UX findings, flows, diagrams, acceptance criteria, and ticket-level
follow-up. It does not promote local/reference behavior to production evidence. Current
completion visuals can communicate a green or complete implementation state while major
production controls remain absent. That is a UX correctness problem, not merely a visual
polish issue. **Production remains NO-GO.**

## Executive findings

### P0 — release-blocking

| ID | Finding | User impact | Required response |
|---|---|---|---|
| UX-P0-1 | Completion and progress visuals conflate implemented reference scope with production readiness. | Operators, reviewers, and customers can infer that a green gate or 100% bar means safe real-data use. | Separate `implemented`, `reference evidence`, and `production qualified` states everywhere. Display NO-GO until production gates pass. |
| UX-P0-2 | Authorization state is not visible at point of search, answer, or citation. | User cannot tell whether result absence means no evidence, no permission, stale projection, or system failure. | Show tenant/source scope, authorization decision, and safe failure reason without exposing protected data. Deny by default. |
| UX-P0-3 | Purge completion can be mistaken for intent or partial progress. | A user may believe deleted content is gone while raw bytes, projections, caches, replicas, or backups remain. | Use explicit lifecycle: requested → running → partial/failed → verified complete. Show per-store receipts and block “complete” on unknown state. |
| UX-P0-4 | Answer experience can imply grounded certainty when citations are incomplete, stale, unauthorized, or absent. | Users may act on unsupported or outdated knowledge. | Deterministic abstention; answer status, evidence age, citation coverage, source scope, and partial-result state must be visible. |

### P1 — release-blocking for applicable MVE scope

| ID | Finding | Required response |
|---|---|---|
| UX-P1-1 | Onboarding does not establish source scope, retention policy, identity boundary, or expected freshness before sync. | Make scope, owner, connector capabilities, retention class, and freshness promise explicit; require confirmation. |
| UX-P1-2 | Sync and projection failures lack a user-recoverable path. | Show last successful checkpoint, current stage, retry/resume action, impact, and escalation owner. Never hide a gap behind a green sync icon. |
| UX-P1-3 | Search does not expose retrieval boundary or freshness. | Provide filters and status for source, document, revision, ACL version, index version, and freshness. Stale results cannot look current. |
| UX-P1-4 | Citation interaction is underspecified. | Every claim must map to authorized source evidence with stable locator, revision, timestamp, and source link where available. |
| UX-P1-5 | Recovery and restore states are operator-only and not connected to user-visible service status. | Publish safe service state, affected scope, recovery phase, and next update; do not disclose sensitive incident detail. |
| UX-P1-6 | Role and privilege boundaries are not represented in navigation or destructive actions. | Apply role-based visibility, explicit scopes, confirmation, and audit context. Do not rely on disabled buttons alone. |
| UX-P1-7 | Error taxonomy collapses denied, unavailable, stale, partial, and insufficient-evidence states. | Use distinct language, icon, color, action, and live-region announcement for each state. |

### P2 — important quality and scale gaps

| ID | Finding | Required response |
|---|---|---|
| UX-P2-1 | No consistent information architecture connects source, document, revision, projection, answer, and purge evidence. | Use stable identifiers and breadcrumbs across surfaces. |
| UX-P2-2 | Completion visuals lack evidence timestamp, owner, scope, and confidence. | Attach evidence metadata to every status component. |
| UX-P2-3 | Empty states do not teach next action or explain safe boundaries. | Add task-oriented empty, first-run, and no-access states. |
| UX-P2-4 | Long-running sync, indexing, purge, and restore tasks need durable status, not transient toasts. | Add activity center with resumable task detail and history. |
| UX-P2-5 | Keyboard, screen-reader, zoom, reduced-motion, contrast, and non-color status behavior are not acceptance-tested. | Adopt accessibility requirements below and include automated plus manual validation. |
| UX-P2-6 | MVE and deferred capability boundaries are not consistently presented. | Label unsupported formats, connectors, answers, and integrations before user invests effort. |

## Product surfaces

| Surface | Primary user | Job | Must communicate |
|---|---|---|---|
| Workspace / home | All roles | Understand what is available and safe | tenant, role, scope, overall state, last update, NO-GO/reference banner |
| Onboarding wizard | Workspace admin | Connect approved source safely | identity, source scope, capability limits, retention, freshness, owner, confirmation |
| Source detail | Admin, operator | Monitor acquisition | connector health, cursor/checkpoint, permissions, last success, lag, errors, retry/resume |
| Document detail | Reader, admin, operator | Inspect knowledge item | source identity, revision, provenance, ACL, processing state, freshness, purge state |
| Search | Authorized reader | Find evidence | scope filters, result state, freshness, authorization, revision, no-result explanation |
| Answer view | Authorized reader | Get grounded response | answer/abstention state, citations, evidence age, partiality, model/reference mode |
| Citation drawer | Reader, reviewer | Verify claim | exact excerpt, source, locator, revision, timestamp, access-safe fallback |
| Ingestion activity | Operator | Diagnose pipeline | stage, queue, lag, checkpoint, projection state, retry, dead letter, owner |
| Purge console | Privacy/admin, operator | Request and verify deletion | policy, scope, impact, confirmation, per-store progress, receipts, exceptions |
| Recovery console | Operator, SRE | Restore service/data safely | incident state, RPO/RTO target, phase, dependencies, validation, traffic state |
| Roles and scopes | Workspace admin, security | Manage access | principal, tenant, source/document scope, role, effective policy, audit trail |
| Readiness / evidence | Reviewer, SRE, product | Decide release | implementation/reference/production classification, dated evidence, owners, blockers, NO-GO |

## Role matrix

| Capability | Reader | Workspace admin | Source admin | Operator/SRE | Privacy/admin | Security/reviewer |
|---|---:|---:|---:|---:|---:|---:|
| Search authorized sources | Yes | Yes | Yes | Break-glass/read-only | Scoped | Review-only |
| View citations | Yes | Yes | Yes | Yes, scoped | Scoped | Yes |
| Connect source | No | Yes, assigned tenant | Yes, assigned source | No | No | Approve |
| Change source scope/permissions | No | Tenant scope | Assigned source | No | No | Approve/audit |
| Retry or pause sync | No | No | Assigned source | Yes | No | Audit |
| View operational diagnostics | No | Limited | Source-scoped | Yes | Purge-scoped | Yes |
| Request purge | No | Policy-scoped | No | Execute only | Yes | Approve/audit |
| Verify purge evidence | No | No | No | Yes | Yes | Yes |
| Restore/recover | No | No | No | Yes, dual control | No | Approve/audit |
| Manage roles | No | Tenant-scoped | No | No | No | Approve/review |
| View audit/evidence | Own actions | Tenant-scoped | Source-scoped | Yes | Purge-scoped | Yes |
| Release readiness decision | No | No | No | Recommend | Privacy sign-off | Approve |

Role labels are UX affordances, not authorization. Server-side policy remains authoritative;
UI must fail closed when identity, policy, or scope is unavailable.

## Information architecture

```text
Workspace
├── Overview
│   ├── Scope and readiness banner
│   ├── Active work
│   └── Recent evidence
├── Knowledge
│   ├── Search
│   ├── Documents
│   │   └── Document → revision → processing → citation → purge history
│   └── Answers
├── Sources
│   ├── Source list
│   ├── Source detail → capabilities → permissions → sync history
│   └── Ingestion activity → checkpoint → projection health
├── Governance
│   ├── Roles and scopes
│   ├── Retention and purge
│   └── Audit and evidence
├── Operations
│   ├── Readiness
│   ├── Recovery
│   └── Runbooks / incidents
└── Help
    ├── Supported formats and connectors
    ├── Status meanings
    └── Accessibility and contact
```

Stable breadcrumb pattern:

```text
Tenant / Source / Document / Revision / Projection or Purge task
```

## Status and completion visual rules

1. Never use one percentage to represent implementation, evidence, and readiness.
2. Every status has scope, timestamp, owner, evidence link, and next action.
3. Use these separate labels: `Implemented locally`, `Reference evidence`, `Production evidence`,
   `Approved for production`, and `Blocked`.
4. Green means only “this narrowly defined check passed.” It never means production-ready.
5. Gray means unknown or not measured, not zero risk.
6. Amber means partial, stale, pending, or requires attention; include exact reason.
7. Red means blocked, failed, denied, or unsafe; include safe recovery action.
8. Purple/outline means deferred or out of scope; it must not resemble completed work.
9. Progress bars show work completion only when denominator and scope are explicit. Evidence
   completion uses checklist items with dated artifacts, not inferred percentages.
10. Gate cards show dependency blockers before celebratory completion metrics.
11. A production banner must remain persistent while any P0/P1 gate is open:

```text
REFERENCE IMPLEMENTATION — NOT PRODUCTION QUALIFIED
Real-data pilot: NO-GO
Open: identity/KMS · authority · purge · recovery · supported load · owners
```

12. “Complete” is permitted only when all required dependencies report verified completion;
    `unknown`, `stale`, `partial`, `failed`, or missing receipt keeps parent state incomplete.

Dependency rule:

```text
child = complete only if evidence is current and verified
parent = complete only if every required child = complete
unknown / stale / failed / denied / partial → parent = blocked or attention-needed
```

## Wireflows and ASCII diagrams

### System surface map

```text
[Identity + tenant scope]
          |
          v
[Onboarding] --> [Source + policy] --> [Sync/checkpoint]
                                      |
                                      v
                          [Authority: accepted state]
                                      |
                         +------------+------------+
                         v                         v
                  [Raw/object store]       [Derived projections]
                         |                         |
                         +------------+------------+
                                      v
                         [Authorized retrieval]
                                      |
                         +------------+------------+
                         v                         v
                    [Evidence]                 [Answer]
                         |                         |
                         +------------+------------+
                                      v
                               [Audit/status]
```

### Onboarding and scope flow

```text
Welcome
  |  explain supported MVE and reference/NO-GO boundary
  v
Choose workspace + confirm role
  |  show tenant, identity provider, effective scope
  v
Select approved source
  |  show format, permissions, connector capabilities, exclusions
  v
Define scope
  |  source folders/items, owner, include/exclude rules
  v
Review retention + freshness
  |  class, purge authority, expected sync cadence, stale behavior
  v
Preview impact
  |  item count estimate, permissions, unsupported items, risk notices
  v
Confirm and connect
  |  explicit consent; no silent broad scope
  v
Sync activity
  |  checkpoint, stage, lag, failures, resume
  v
Ready for search only after authority + policy + projection freshness gates pass
```

### Freshness and retrieval flow

```text
User query
   |
   v
Resolve identity / tenant / source scope
   |-- unavailable or ambiguous --> DENIED / TRY AGAIN
   v
Apply ACL + tombstone + revocation before retrieval limits
   |-- no authorized scope ----------> NO ACCESS (not “no documents”)
   v
Retrieve from derived projection
   |-- projection stale --------------> STALE result state / block or explicit opt-in
   |-- projection unavailable ---------> UNAVAILABLE / retry or browse authority
   v
Check revision, freshness, evidence completeness
   |-- insufficient evidence ----------> ABSTAIN with next action
   v
Return authorized results + source/revision/time
```

### Answer and citation flow

```text
Question
  v
Scope + policy check
  |-- denied -------------------------> Explain scope-safe denial
  v
Retrieve authorized evidence
  |-- none ----------------------------> “I don't have enough authorized evidence.”
  |-- stale ---------------------------> Mark stale; do not present as current
  |-- partial -------------------------> Mark partial; list missing scope
  v
Grounded answer assembly (bounded planner/model)
  |-- citation mismatch ---------------> Suppress claim; abstain
  v
Answer with:
  [status] [answer] [citations] [evidence age] [scope] [limitations]
  |
  v
Citation drawer → exact excerpt → source → revision → timestamp → authorized link
```

### Purge flow

```text
Request deletion
  v
Select scope + retention reason + effective time
  v
Impact preview: raw / authority / projections / caches / replicas / backups
  |-- scope ambiguous -----------------> stop; request clarification
  v
Second confirmation / required approver
  v
Create purge intent + tombstone
  v
Run idempotent deletion workflow
  +--> raw bytes
  +--> accepted state
  +--> FTS/vector projections
  +--> caches / derived artifacts
  +--> backup/replica treatment per policy
  +--> audit-linked evidence
  v
Collect per-store receipts
  |-- missing / failed / unknown ------> INCOMPLETE; retry/escalate; never “done”
  v
Negative retrieval test + restore-after-purge check
  |-- any residual --------------------> FAILED / investigate / keep tombstone
  v
Verified complete
```

### Recovery flow

```text
Detect outage or integrity event
  v
Declare incident + affected scope
  v
Show service state: unavailable / degraded / read-only / recovering
  v
Freeze unsafe writes and preserve tombstones/policy
  v
Restore authority first
  v
Validate keys, schema, outbox, checkpoints, ACLs
  v
Restore raw references; rebuild or validate projections
  v
Run authorization, citation, freshness, purge, and smoke checks
  |-- failed --------------------------> remain recovering; escalate
  v
Return traffic gradually
  v
Publish recovery evidence: RPO, elapsed time, affected scope, validation, owner
```

### Failure-state matrix

| State | Meaning | User copy pattern | Allowed action |
|---|---|---|---|
| Unavailable | Dependency or service cannot answer | “Service unavailable. No result was returned.” | Retry, inspect status, escalate |
| Denied | Principal lacks access or policy fails closed | “You do not have access to this scope.” | Request access; never reveal existence |
| Stale | Data or ACL projection exceeds freshness policy | “Results may be stale as of `<time>`.” | Refresh, narrow scope, wait |
| Partial | Some authorized work completed, some failed | “Partial results; `<n>` sources unavailable.” | Inspect details, retry failed work |
| Insufficient evidence | Authorized evidence cannot support answer | “I don’t have enough evidence to answer.” | Broaden authorized scope, improve source, ask narrower question |
| Purge incomplete | Deletion not verified across required stores | “Deletion is still in progress or needs attention.” | Retry/escalate; no completion claim |
| Recovering | Service restoration underway | “Service is recovering; writes/search may be limited.” | Monitor status; operator follows runbook |

## Onboarding, scope, freshness, retrieval, citation, answer, purge, and recovery requirements

### Onboarding and scope

- Make supported formats explicit: UTF-8 plain text, Markdown, CSV, and one approved text
  connector for MVE.
- Mark images, PDFs, OCR, attachments, email, vectors, MCP, and unapproved connectors as deferred.
- Show source permissions before sync. A connector must not silently widen tenant or source scope.
- Make retention class, purge owner, expected freshness, and stale-result behavior required setup data.
- Preview unsupported items and estimated scope before authorization.
- Preserve source identity, cursor/checkpoint, revision, actor, and correlation ID in activity detail.

### Freshness and retrieval

- Display last successful source sync, authority update, projection update, ACL version, and index version.
- Distinguish source freshness from projection freshness and authorization freshness.
- Never use “latest” without timestamp and scope.
- Stale ACL or tombstone state blocks unsafe retrieval; stale content may be shown only with explicit policy-approved labeling.
- Filters apply before ranking, limiting, context expansion, planner tools, caches, and model input.
- No result must not reveal whether inaccessible content exists.

### Citation and answer

- Default answer mode is deterministic abstention.
- Generated answers require explicit local/reference model opt-in and citations; this does not authorize production data.
- Cite source, document, stable locator, revision, evidence timestamp, and relevant excerpt.
- Citation drawer must preserve authorization checks; citation URLs cannot become access bypasses.
- Label answer as grounded, partial, stale, or abstained. Do not style abstention as failure when it is safe behavior.
- Model or planner output cannot grant access, select unauthorized sources, or become authority.
- Explain what user can do next: narrow question, request access, wait for sync, or inspect source.

### Purge and recovery

- Purge request must show scope, retention reason, dependencies, irreversible effects, and approval requirement.
- Keep tombstone/revocation visible to operators until all required deletion receipts and negative tests pass.
- Retain evidence needed to prove deletion without retaining deleted content beyond policy.
- Recovery UI must expose RPO/RTO targets, observed values, validation phases, and unresolved checks.
- Restore/replay must not resurrect tombstoned or revoked content.
- User-facing status must be safe, scoped, and timestamped; operator details belong behind role checks.

## Accessibility requirements

1. Meet WCAG 2.2 AA for all MVE surfaces.
2. Support complete keyboard operation, visible focus, logical focus order, skip links, and no keyboard trap.
3. Provide semantic headings, landmarks, labels, descriptions, table headers, and programmatic relationships.
4. Announce async sync, retrieval, purge, and recovery state changes through appropriate live regions without repeated noise.
5. Do not encode status by color alone. Pair color with text, icon, shape, and accessible name.
6. Maintain contrast for text, controls, focus indicators, disabled/amber/red states, and status banners.
7. Support 200% zoom and reflow without hiding status, scope, citations, or destructive controls.
8. Support reduced motion. Never require animation to understand progress or failure.
9. Provide accessible alternatives for diagrams, progress bars, charts, and dense activity timelines.
10. Keep error messages adjacent to fields, specific, persistent, and associated programmatically.
11. Preserve copy/paste and text selection for citations; do not make evidence image-only.
12. Respect screen-reader reading order in result cards, citation drawers, dialogs, and toasts.
13. Destructive actions require accessible confirmation with scope, consequences, and cancel path.
14. Test with keyboard-only, VoiceOver/NVDA, zoom, high contrast, reduced motion, and touch targets.
15. Localization-ready strings must not rely on fixed width, color semantics, or concatenated sentence fragments.

## MVE versus deferred UX

### MVE

- Text-first ingestion: UTF-8 plain text, Markdown, CSV, one approved text connector.
- Authenticated, scoped source onboarding with explicit permissions and retention/freshness display.
- Search over authorized evidence with freshness and safe empty/denied states.
- Deterministic abstention by default; explicit local/reference answer opt-in with citations.
- Source/document/revision provenance and citation inspection.
- Sync status, checkpoint, projection status, retry/resume, and operational ownership.
- Retention, deletion, purge progress, receipts, incomplete state, and recovery evidence surfaces.
- Readiness surface that clearly separates reference completion from production qualification.
- Keyboard and screen-reader accessible critical flows.

### Deferred

- Images, PDFs, OCR, attachments, email, vectors as user-facing scope, and MCP.
- Broad connector marketplace, autonomous agent actions, uncited answer modes, and model-selected access.
- Rich collaboration, saved searches, personalization, recommendations, and nonessential analytics.
- OpenSearch UI or second-index controls before measured trigger and separate security/operations review.
- Production pilot UX approval before real OIDC/KMS, PostgreSQL authority, purge, recovery, load,
  SLO/RPO/RTO, observability, and named-owner gates close.

Deferred does not mean rejected. Deferred capabilities must not appear as available or complete.

## UX acceptance criteria

| ID | Acceptance criteria |
|---|---|
| UX-01 | Every readiness/progress surface separates implementation, reference evidence, and production qualification; scope, timestamp, owner, evidence, blockers, and next action are visible. |
| UX-02 | Onboarding requires authenticated tenant/role scope, approved source, permissions, retention class, purge owner, freshness expectation, impact preview, and explicit confirmation before sync. |
| UX-03 | Search applies authorization, tombstone, and revocation before ranking/limiting/context expansion and presents distinct denied, unavailable, stale, partial, and insufficient-evidence states. |
| UX-04 | Search and document views show source, revision, authority timestamp, projection timestamp, ACL/index versions, and freshness policy without exposing unauthorized existence. |
| UX-05 | Every generated answer is either grounded with authorized citations or deterministic abstention; citation drawer shows stable locator, excerpt, revision, timestamp, and access-safe failure. |
| UX-06 | Sync/projection activity exposes stage, checkpoint, last success, lag, failure reason, retry/resume, owner, and affected scope; unresolved gaps cannot display as complete. |
| UX-07 | Purge flow shows impact and approvals, creates visible intent/tombstone, reports per-store receipts, supports idempotent retry, and cannot report complete for unknown/failed/missing deletion or restore-after-purge validation. |
| UX-08 | Recovery flow shows incident state, affected scope, RPO/RTO target and observed values, recovery phase, dependencies, validation checks, traffic state, owner, and safe next update. |
| UX-09 | Role-based navigation and destructive actions match server-side deny-by-default policy; keyboard, screen-reader, zoom, contrast, reduced-motion, and non-color status tests pass for critical flows. |
| UX-10 | MVE/deferred boundaries are visible and accurate; all P0/P1 UX findings have dated evidence, named owners, and independent parent validation; production banner remains NO-GO until product/security/operations gates pass. |

## Phase 3 tickets

| Ticket | Work | Done when |
|---|---|---|
| UX-301 | Implement readiness state model with separate implementation/reference/production statuses. | Status components consume typed state and cannot infer production readiness from test count or percentage. |
| UX-302 | Add persistent NO-GO/reference banner and blocker panel. | Banner appears on home, readiness, source, search, and answer surfaces while gates remain open. |
| UX-303 | Build onboarding scope and capability wizard. | Supported formats, connector limits, permissions, tenant scope, and unsupported items are reviewed before sync. |
| UX-304 | Add retention, freshness, and purge-owner setup step. | Setup cannot finish without policy values or explicit blocked state and owner. |
| UX-305 | Add source detail and sync activity center. | Checkpoint, lag, stage, retries, dead letters, owner, and affected scope are durable and inspectable. |
| UX-306 | Implement freshness metadata and stale-state components. | Source, authority, projection, ACL, and index timestamps render separately with policy-based stale behavior. |
| UX-307 | Implement deny-safe search states. | Denied, unavailable, stale, partial, and no-authorized-content states have distinct copy, action, and telemetry. |
| UX-308 | Enforce pre-ranking authorization UX contract. | UI/API integration tests prove scope filters precede limits, context expansion, planner, cache, and answer. |
| UX-309 | Build document/revision provenance view. | User can trace source → document → revision → projection with stable IDs and access checks. |
| UX-310 | Build citation drawer and claim mapping. | Claims map to authorized excerpts, locators, revisions, timestamps, and safe unavailable states. |
| UX-311 | Implement deterministic abstention and answer-state components. | Insufficient evidence, stale evidence, partial evidence, and model/reference opt-in are explicit. |
| UX-312 | Add bounded planner/model disclosure. | Answer view shows mode, limitations, citations, and cannot imply model output is authority. |
| UX-313 | Implement purge request and impact preview. | Scope, dependencies, retention reason, consequence, approver, and irreversible action are reviewable. |
| UX-314 | Implement purge progress and receipt view. | Per-store status, retries, failures, unknowns, tombstone state, and final verification are visible. |
| UX-315 | Add restore-after-purge and negative-retrieval evidence panel. | “Complete” requires all configured receipts plus verification; residual/unknown state blocks completion. |
| UX-316 | Build recovery/status communication surface. | Operators and users receive role-appropriate incident, affected-scope, RPO/RTO, phase, and update information. |
| UX-317 | Implement role/scope matrix in navigation and action guards. | UI visibility matches policy decisions; server remains authoritative; break-glass actions are audited. |
| UX-318 | Complete accessibility implementation and test harness. | WCAG 2.2 AA critical-flow checks pass with keyboard, screen-reader, zoom, contrast, and reduced-motion evidence. |
| UX-319 | Add UX telemetry and evidence links. | Status transitions include correlation ID, scope, owner, timestamp, reason, and reviewable artifact without sensitive payloads. |
| UX-320 | Run cross-functional UX readiness review. | Product, security, SRE, privacy, and parent validation sign dated evidence; unresolved P0/P1 findings keep production NO-GO. |

## Phase 3 exit condition

Phase 3 UX work exits only when UX-01 through UX-10 pass with dated, reviewable evidence;
UX-301 through UX-320 are implemented or explicitly accepted with named owner and due date;
critical flows pass accessibility review; and product, security, operations, privacy, and
parent validation owners approve the same scope.

Exit does **not** independently authorize production. Production remains **NO-GO** until
the broader gates also prove real OIDC/JWKS, real KMS and encrypted read path, PostgreSQL
authority, authorized tenant/source boundaries, cross-store purge, backup/restore and
RPO/RTO, supported-runtime load and SLO evidence, deployment/observability/runbooks,
accepted connectors/projections, and named ownership. UX completion visuals must continue
to show those dependencies as open.

```text
PHASE 3 UX EXIT
IA / roles             [░░░░░░░░░░] pending implementation
Onboarding / scope     [░░░░░░░░░░] pending implementation
Freshness / retrieval  [░░░░░░░░░░] pending implementation
Answer / citation      [░░░░░░░░░░] pending implementation
Purge / recovery       [░░░░░░░░░░] pending production evidence
Accessibility          [░░░░░░░░░░] pending validation
Cross-functional signoff [░░░░░░░░] pending
PRODUCTION             [░░░░░░░░░░] NO-GO
```

## Recovery limits

Parent context did not remain available as a retrievable transcript in current workspace
session. This file preserves requested UX topic coverage and the complete findings supplied
by task context, but exact source-agent prose, additional diagrams, ticket wording, numeric
UX thresholds, screenshots, and any omitted parent-only detail are unrecoverable here. They
must not be inferred or treated as approved requirements. Existing repository evidence is
reference/local scope and does not change the production **NO-GO** decision.
