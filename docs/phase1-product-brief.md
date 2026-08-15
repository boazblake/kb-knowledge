# Phase 1 Product Brief

```text
+--------------------------------------------------------------+
| STATUS: FINDINGS COMPLETE                         PROD: NO-GO |
| DONE: text-first MVE, gates, migration order, Python retained|
| OPEN: retention/purge owner; roles; load/SLO/RPO/RTO values   |
| BLOCKERS: real OIDC/KMS; PostgreSQL authority; purge; recovery|
| NEXT: assign owners, record thresholds, execute hardening     |
+--------------------------------------------------------------+
```

## Research record standard

- Full findings remain below; this record adds status and current-direction context without deleting substantive material.
- Record metadata must name agent role, date, source or source set, and validation owner.
- Label agent findings separately from recommendations. Article claims, where present, must remain separate from recommendations and repository facts.
- Keep unresolved decisions explicit. No silent resolution, inference, or acceptance approval is allowed.

> **Provenance:** Product-manager agent; Phase 1; 2026-08-15; validation owner: Parent.
>
> **Editorial note:** Sections headed **Agent finding** preserve Phase 1 findings. Headings, ordering, cross-references, and the recovery note are editorial organization. No contradiction is resolved here.

## 1. Product direction

**Agent finding.** Build text-first, production-shaped minimum viable experience (MVE). Limit custom code to authority, policy, provenance, citation, and thin API surfaces. Adopt production components instead of extending prototype substitutes. Do not rewrite in Go. Retain existing Python policy and contract layer. Harden before expanding scope.

## 2. MVE content scope

**Agent finding.** Initial scope:

- UTF-8 plain text
- Markdown
- CSV
- One approved text connector

Deferred: images, PDFs, OCR, attachments, email, vectors, and MCP. Do not broaden content scope while prototype substitutions remain.

## 3. Users and jobs

**Agent finding.** MVE must support authorized text search, source and citation provenance, grounded answers, explicit abstention when evidence is insufficient, purge behavior, and recovery/evidence suitable for operations and review.

Required roles and access model must be defined before production approval.

## 4. Access and security posture

**Agent finding.** Tenant and source ACL enforcement is deny-by-default. Production approval requires real OIDC, real KMS, identity/authorization review, tenant/source isolation, and required role definitions and grants. Fake ACL, fake OIDC, and fake KMS are prototype substitutions, not production controls.

## 5. Answer behavior

**Agent finding.** Answers must be grounded in authorized evidence, return provenance and citations, and abstain explicitly when evidence is insufficient. Model output cannot grant access or become source truth.

## 6. Retention and purge

**Agent finding.** MVE requires retention, deletion, purge, and purge evidence. Retention classes, purge policy, and accountable owner remain unresolved product decisions. Phase 2 must assign an owner and record policy before Phase 2 closes.

## 7. Recovery and evidence

**Agent finding.** MVE requires recovery process and evidence. Production approval requires authoritative persistence, verified purge, recovery evidence, load/service-objective validation, explicit RPO and RTO, and required approvals.

## 8. Acceptance plan

**Agent finding.** Acceptance gates:

| Gate | Required coverage |
|---|---|
| **SEC** | Security, identity, authorization, tenant/source isolation, and key management |
| **ING** | Approved connector and ingestion correctness |
| **ANS** | Grounded answer, citation, and abstention behavior |
| **PUR** | Retention, deletion, and purge evidence |
| **OPS** | Recovery, evidence, operational readiness, load, and service objectives |

Exact load, SLO, RPO, and RTO thresholds must be agreed and recorded.

## 9. Release decision

**Agent finding.** MVE remains **NO-GO** until all following exist and pass validation:

- Real OIDC
- Real KMS
- Authoritative persistence
- Verified purge
- Recovery process and evidence
- Load and service-objective validation
- Explicit RPO and RTO
- Required approvals

## 10. Migration order

**Agent finding.** Retire prototype substitutions in this order:

1. Fake ACL and fake OIDC.
2. Fake KMS.
3. SQLite as authority.
4. Local connector.
5. Custom parser and index.
6. Backup implementation.
7. Direct Ollama integration.

Keep Python contracts stable while replacing implementations behind them.

## 11. Migration constraints

**Agent finding.** Hardening comes first. Production components replace prototype substitutions behind stable contracts. No Go rewrite. No scope expansion while fake identity/KMS, SQLite authority, local connector, custom parser/index, incomplete backup, and direct model integration remain.

## 12. Product acceptance evidence

**Agent finding.** Evidence must cover security, ingestion, grounded answers/citations/abstention, retention/deletion/purge, recovery, operations, load, service objectives, RPO, and RTO. Test results without production integrations, approved thresholds, named ownership, and review do not clear the NO-GO decision.

## 13. Operational ownership

**Agent finding.** Product decisions still need accountable owners for retention classes, purge policy, required roles/access grants, and numeric load/SLO/RPO/RTO thresholds. Operations must be able to review recovery and purge evidence.

## 14. Deferred capabilities

**Agent finding.** Images, PDFs, OCR, attachments, email, vectors, and MCP are deferred from initial content scope. Deferral is not rejection; no Phase 1 decision authorizes adding them.

## 15. Implementation boundary

**Agent finding.** Python remains semantic policy and contract layer. Custom responsibility is limited to authority, policy, provenance, citation, and thin API surfaces. Commodity infrastructure belongs behind adapters/contracts.

## 16. Decisions requiring Phase 2

**Agent finding.** Phase 2 must decide, without silently merging recommendations:

- Vector/search default: product manager recommends **pgvector default**; architect recommends **OpenSearch as initial target** for hybrid retrieval.
- Retention classes, purge policy, and accountable owner.
- Required role definitions and access grants.
- Numeric load, SLO, RPO, and RTO thresholds.

**Current locked direction.** Initial retrieval uses **pgvector plus PostgreSQL full-text search**. OpenSearch is deferred until a measured scale, latency, operational-isolation, or retrieval-feature trigger is recorded. Historical recommendations remain preserved; retention, roles, and operational thresholds remain unresolved.

## 17. Unresolved findings and recovery limits

**Agent finding.** Phase 1 output available for this rewrite records complete MVE scope, required outcomes, acceptance gates, migration order, NO-GO criteria, and unresolved decisions above. Full terminal transcript containing any additional product-manager prose, examples, or exact subsection text was not available in workspace context; it cannot be reproduced safely. No missing material is silently resolved.
