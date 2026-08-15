# Phase 4 core dev/mock evidence runbook

`production_qualification=false`.

Evidence run: `phase4-20260815T214315Z-38130` at clean checkpoint
`e3710e33139d4f13545b158a97d1ea1292af700a`.

## Scope and limitations

E2E-001..E2E-010 and P4-01..P4-11 use PostgreSQL, psycopg, PostgreSQL FTS,
injected adapter ports, mock `Principal`/provider fixtures, and a reference
frontend surface. MOCK/REFERENCE only: no live auth, provider calls, cloud,
custom infrastructure, production concurrency, SLO, RPO, or RTO claim.

Source-spec artifacts for labeled E2E/P4 scenarios are absent. Labels map to
available repository evidence; they do not substitute for missing
Given/When/Then source specs. Frontend remains observational and read-only.

## Executed evidence

| Field | Current fact |
|---|---|
| Commit | `e3710e33139d4f13545b158a97d1ea1292af700a` |
| Evidence run | `phase4-20260815T214315Z-38130` |
| Runtime | Nix Python 3.11.11; Node v22.16.0; disposable PostgreSQL 16; HeadlessChrome 149 |
| Schema | `migrations/006_phase4_projection.sql` |
| Migrations | 1, 2, 3, 4, 5, 6 applied; second run no-op; pass |
| Nix full suite | 200 passed / 0 skipped |
| Disposable PostgreSQL full suite | 200 passed / 0 skipped |
| Targeted Phase 4 | 14 passed / 0 failed |
| Labeled scenarios | 21/21 pass: E2E-001..E2E-010 and P4-01..P4-11 |
| Browser/accessibility | Pass |
| P1 defects | None |
| P2 artifacts | Source-spec artifacts absent |
| P3 defects | Favicon 404 |
| Coverage | Not measured |

Evidence ledger: `phase4-qa-bdd-ledger-2026-08-15.json`.

Temporary evidence path: `/tmp/phase4-20260815T214315Z-38130`.

Temporary artifact checksums and executed commands are recorded in the checked-in
ledger. Screenshot capture deviated: no screenshot artifact was available;
browser snapshot, accessibility, and network evidence were captured instead.
No production deployment or production scans were run.

## Reproducible checks

```sh
python3 -m compileall -q kb_pipeline tests
python3 -m unittest discover -s tests -p 'test*.py'
```

Set `P3_POSTGRES_DSN` to run PostgreSQL integration scenarios. Without it,
PostgreSQL-specific tests skip by design; SQLite tests do not qualify the
PostgreSQL path. Current evidence used disposable PostgreSQL and recorded
zero PostgreSQL skips.

## Evidence map

| Ticket | Evidence |
|---|---|
| P4-01/02 | `kb_pipeline/phase4_core.py`, semantic identity and deterministic envelope tests |
| P4-03/06 | `migrations/006_phase4_projection.sql`, `tests/test_p4_postgres_integration.py`, projection/barrier contracts |
| P4-04/05 | `security.py`, `phase4_core.py`, `tests/test_p4_postgres_integration.py`, tenant/ACL-before-limit query contract |
| P4-07/08 | `tests/test_p4_postgres_integration.py`, tombstone revision guards and citation verification contracts |
| E2E-007/P4-09 | `tests/test_p4_postgres_integration.py::test_e2e007_p4_09_retry_bounded_dlq_authorized_recovery_and_tombstone`; deterministic three-attempt injection, durable DLQ, operator replay, explicit watermark/barrier transition, authority invariant, and tombstone non-resurrection |
| P4-10 | this runbook and generated test output |
| P4-11/E2E-009/E2E-010 | `frontend/project-visualization.html`, `frontend/project-visualization.js`, `tests/test_phase4_qa.py`, browser/accessibility evidence; read-only observation surface |

Known gaps: P2 source-spec artifacts absent; P3 `/favicon.ico` returns 404;
coverage not measured. Production PostgreSQL concurrency, live identity, cloud
storage, provider realism, measured SLO/RPO/RTO, and production qualification
remain out of scope.
