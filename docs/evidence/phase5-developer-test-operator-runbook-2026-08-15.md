# Phase 5 developer and test-operator runbook

Status: **development/mock only**. `production_qualification=false`.

Milestone disposition: code review **PASS**; BDD **PASS**; SRE **conditional
developer GO / scripted QA only**; production **NO-GO**.

This runbook describes repeatable local checks and safe recovery exercises. It
does not authorize production deployment, provider access, or customer data.

## Evidence identity

- Current application commits: through `18a4c39`; frontend visual fix:
  `1f5f331`.
- Evidence was tested at `397911e` (full commit
  `397911e01029c8e626d98b9661263f8a2f7ff00c`), which is an ancestor of HEAD.
- Worktree is dirty only because excluded `frontend/repository-metrics.json`.
  Do not include that file in evidence.
- Checked-in visual metadata still identifies snapshot HEAD as `314eb94`; treat
  it as prior snapshot metadata, not current application provenance. The visual
  surface remains read-only/observational.
- Providers are mock/reference providers. Live provider qualification: not run.
- Migration provenance: fresh database applied migrations **1..7**; second run
  was a no-op. Record database, run ID, commit, and migration output together.

Recorded evidence run IDs:

| Surface | Run ID | Result and boundary |
|---|---|---|
| Nix, no DSN | `phase5-nix-20260815-397911e` | 221 passed / 34 skipped / 0 failed; PostgreSQL cases skipped by design |
| Fresh disposable PostgreSQL | `phase5-pg-20260815-397911e` | 221 passed / 0 skipped / 0 failed; synthetic local integration only |
| Browser snapshot/BDD | `phase4-20260815T214315Z-38130` | browser/a11y/network evidence; no production scan; screenshot unavailable |

`phase5-nix-*` and `phase5-pg-*` are documentation run IDs assigned to the
recorded Phase 5 results; retain raw command output and database identity with
them. They are not claims of a provider or production run.

## Hard safety boundary

Use synthetic fixtures only. Do not place customer, confidential, regulated,
email, attachment, credential, or production connection data in files, DSNs,
logs, traces, screenshots, temporary directories, or evidence bundles. Use a
fresh disposable PostgreSQL instance for each integration run. Never point
these commands at shared or production PostgreSQL.

## Developer checks

Enter pinned environment:

```sh
nix develop
```

Run local suite, syntax checks, and packaged checks:

```sh
python -m unittest discover -v
python -m compileall -q kb_pipeline tests
node --check frontend/app.js
nix flake check
nix run .#check
```

Run frontend BDD. This starts a loopback static server and uses a dependency-
free browser BDD script; it must remain observational/read-only:

```sh
bash tests/frontend_project_visualization_bdd.sh
```

Expected frontend result: **9 passed, 0 failed**; overall BDD status:
**PASS**. A missing `agent-browser` is a skipped prerequisite, not a pass.

## Safe lifecycle test sequence

Run against synthetic identifiers in one fresh disposable environment:

1. **Create**: accept new object, raw reference, authority row, audit event, and
   outbox event. Proves ingestion acceptance and atomic handoff.
2. **Update**: submit higher revision. Proves revision ordering and projection
   advancement.
3. **Duplicate**: replay same revision/payload. Proves idempotency without a
   second authority effect.
4. **Conflict**: submit same identity/revision with different payload. Proves
   quarantine/fail-closed conflict handling.
5. **Delete**: emit delete, retain tombstone, and process projection. Proves
   deletion wins over stale delivery.
6. **Replay**: replay bounded outbox/ledger history after failure. Proves
   checkpoint repair, no resurrection, and citation/provenance revalidation.

Do not reorder steps, skip conflict, or use direct SQL to advance checkpoints.
Purge and DLQ replay remain separate operator exercises below.

## What pipeline stages prove

| Stage | Evidence proves | Does not prove |
|---|---|---|
| Connector/canonicalization | stable synthetic identity, UTF-8 normalization, cursor/revision/delete contracts | live provider behavior or credentials |
| Authority/ledger | accepted state, revision guards, tombstones, audit and outbox contract | production PostgreSQL HA or multi-writer safety |
| Outbox/workflow | bounded claims, retry/DLQ/replay semantics | Temporal deployment or host-loss recovery |
| Projection/barrier/search | derived FTS state, ACL filtering, watermark/freshness gates | production capacity or SLO |
| Purge/recovery | receipts, no-resurrection, bounded repair | cross-system production erasure guarantee |
| Frontend/browser | read-only rendering, accessibility, stale/failed states, no mutation request | backend correctness or visual production readiness |

Each stage uses mock/reference providers and synthetic data. Passing stage
evidence cannot be composed into production qualification.

## Disposable PostgreSQL run

Use an isolated temporary data directory, socket, and port. The following is
the recorded run shape; replace placeholders with temporary values and remove
them on exit:

```sh
nix develop -c bash -c 'set -euo pipefail
PGDATA=$(mktemp -d /tmp/kb-pg.XXXXXX)
SOCK=$(mktemp -d /tmp/kb-sock.XXXXXX)
PORT=<unused-local-port>
initdb -D "$PGDATA" -A trust --no-locale --encoding=UTF8
pg_ctl -D "$PGDATA" -o "-p $PORT -k $SOCK" -w start
trap "pg_ctl -D \"$PGDATA\" -m immediate stop; rm -rf \"$PGDATA\" \"$SOCK\"" EXIT
P3_POSTGRES_DSN="postgresql://$USER@localhost:$PORT/postgres" \
  python -m unittest discover -s tests -p "test*.py" -v
python -m compileall -q kb_pipeline tests
node --check frontend/*.js'
```

Apply migrations against this database in order. Capture the migration-runner
output for pass 1 and pass 2:

```text
MigrationRunner().run(connection)       # fresh run: 1,2,3,4,5,6,7
MigrationRunner().run(connection)       # second run: no-op
```

Label results by environment and run, never as an unqualified test count.
Expected current counts:

| Environment/run | Expected result |
|---|---:|
| Nix suite, no PostgreSQL DSN | 221 passed / 34 skipped / 0 failed |
| Fresh disposable PostgreSQL suite | 221 passed / 0 skipped / 0 failed |
| Frontend BDD | 9 passed / 0 failed |

## Operator procedures

Procedures below are reference procedures for a disposable development run.
They are not production controls.

### Outbox stall or lease expiry

1. Stop intake and record tenant, workload, run ID, current authority sequence,
   pending/claimed/dead counts, and checkpoint watermarks.
2. Inspect pending rows ordered by sequence. Do not edit payload, authority, or
   checkpoint rows.
3. Run the outbox reconciler with an explicit worker, tenant, workload, and
   bounded limit (`reconcile_outbox(..., worker, tenant, workload, limit<=100)`).
4. Reconciler claims rows with a lease; mark applied only after workflow start.
   Failures return to pending with bounded backoff; expired claims become
   claimable again.
5. Verify pending count falls, applied sequence is monotonic, and authority is
   unchanged. Escalate if lease ownership, tenant/workload scope, or sequence
   invariants fail.

### Checkpoint or gap issue

1. Freeze intake for affected tenant/workload and capture authority head,
   checkpoint, gap, and projection status.
2. Find first missing sequence; do not skip it and do not advance checkpoint by
   direct SQL.
3. Reconcile outbox from first missing sequence, then replay bounded batches.
4. Check checkpoint monotonicity and contiguous acceptance. Resume only when
   gap is clear and authority/projection counts agree.

### Projection barrier not fresh

1. Treat `pending`, `stale`, `blocked`, and `timeout` as unsafe for freshness.
2. Compare required authority sequence with each projection watermark.
3. Process/replay outbox for missing sequences; preserve tombstones and revision
   guards. Recheck barrier after each bounded batch.
4. Do not report search freshness while barrier is below required sequence.
   Escalate repeated failure, watermark regression, or authority mutation.

### Dead-letter replay

1. Stop automatic recovery for affected workload; inspect sequence, tenant,
   reason, attempts, and last error.
2. Identify root cause and obtain an operator principal with tenant-scoped admin
   authorization.
3. Replay one item only with explicit operator identity:
   `manual_retry_dead_letter(repository, sequence, operator=operator)`.
4. Verify audit event `dlq-replay`, status `pending`, attempts reset, successful
   workflow acceptance, projection watermark, and unchanged authority.
5. Never bulk-replay, bypass authorization, or delete DLQ evidence. Escalate
   poison payloads and repeated terminal failures.

### Projection repair

1. Stop reads that require freshness and capture affected projection/watermark.
2. Rebuild from authoritative ledger using bounded replay
   (`engine.replay(rebuild=True)` in local reference path).
3. Apply projection and checkpoint in one transaction; require contiguous
   sequence. Replay must preserve tombstones and never resurrect deleted data.
4. Validate citation revision, content hash, ACL scope, barrier state, and
   projection counts before reopening reads.

### Purge and receipt verification

1. Create a scoped purge intent with actor, correlation ID, target, policy, and
   run ID. Confirm authorization and retention policy before execution.
2. Tombstone authority target first. Execute provider/reference deletion across
   authority, raw object, projection, cache, workflow state, and backup replica
   scopes as applicable.
3. Save one receipt per store; inspect `purge_status` and `purge_receipts`.
4. Confirm audit record, artifact absence, projection absence, and replay
   no-resurrection. Leave incomplete status for any failed store; never mark
   complete manually.
5. Escalate missing receipts, cross-tenant candidates, or any raw artifact that
   remains reachable.

### Telemetry and escalation

Record run ID, environment, commit, tenant/workload **synthetic identifiers**,
operation, outcome, retryability, attempt, status, and error type. Never record
payloads, raw content, tokens, credentials, authorization headers, DSNs, or
full object identifiers.

Mock telemetry sinks and redaction tests are not proof that a real collector,
backend, exporter, retention policy, or access control redacts data. Use only
synthetic data; production OTLP wiring requires separate security/SRE review.

Escalate immediately on authority mutation, sequence/checkpoint regression,
cross-tenant visibility, failed purge receipt, unexplained DLQ growth, unsafe
barrier state, telemetry leakage, or any need to use non-mock providers.

## Troubleshooting

| Symptom | Action |
|---|---|
| PostgreSQL tests skipped | Set `P3_POSTGRES_DSN` to isolated disposable PostgreSQL; do not count skipped Nix tests as PostgreSQL evidence. |
| Migration rerun changes state | Stop. Preserve logs and database; expected second run is no-op. Check migration provenance. |
| BDD reports skipped | Install/enable `agent-browser`; rerun script. Do not label skip as PASS. |
| Barrier remains stale | Inspect first missing outbox sequence and projection watermark; replay bounded batches; never skip. |
| DLQ item cannot replay | Verify item is terminal/dead and operator is tenant-scoped admin; keep item for escalation. |
| Purge incomplete | Keep intent incomplete, inspect receipts by store, and escalate. Do not delete evidence. |
| Telemetry package/export fails | Keep local run synthetic; record unavailable telemetry. Do not substitute mock sink for production observability. |

## Evidence artifacts

- [`phase5-evidence-summary-2026-08-15.md`](phase5-evidence-summary-2026-08-15.md)
- [`frontend/visualization-status.json`](../../frontend/visualization-status.json)
- [`phase4-qa-bdd-ledger-2026-08-15.json`](phase4-qa-bdd-ledger-2026-08-15.json)
- [`phase4-core-runbook-2026-08-15.md`](phase4-core-runbook-2026-08-15.md)
- [`mock-connector-qualification-2026-08-15.md`](mock-connector-qualification-2026-08-15.md)
- [`GATE5_QA_RESULTS.json`](../../GATE5_QA_RESULTS.json)
- [`GATE6_SRE_RESULTS.json`](../../GATE6_SRE_RESULTS.json)
