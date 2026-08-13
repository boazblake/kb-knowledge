# MVP pilot plan and acceptance

## Objective

Turn local plaintext demo into a narrowly scoped pilot without claiming target BII
capabilities. Email, attachments, vectors, relationships, MCP, and LLM remain out
of MVP unless separately approved.

## Required sequence

1. Identity/ACL boundary and encryption.
2. Atomic single-writer workflow plus durable outbox/replay and migrations.
3. Source-scoped deletion and complete provenance/freshness/citations.
4. Atomic backup/restore with RPO/RTO rehearsal.
5. Enforced limits, monitoring, alerts, deployment, and on-call.
6. Correct API/UI integration and pilot data onboarding controls.

## Acceptance gates

| Gate | Pass evidence |
|---|---|
| Security | Real identity mapping; deny-by-default tests; encryption/key review; tenant and secret review |
| Durability | Restart/crash/concurrency tests; no inconsistent document/FTS5/audit state; replay proves recovery |
| Deletion/provenance | Source deletion test covers raw, projections, backup/cache policy; result traces source, transform, time, citation |
| Recovery | Locked consistent backup; restore to clean host; artifact/index validation; measured RPO/RTO |
| Operations | Limits tested; health/readiness, metrics, alerts, logs, capacity and on-call runbook exercised |
| Product scope | API/UI route contract passes; local plaintext scope documented; privacy/accessibility/fresh-data sign-off |

Pilot remains NO-GO until every gate has named owner, dated evidence, and approval.
