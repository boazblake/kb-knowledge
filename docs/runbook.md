# Demo runbook and remediation order

## Safe demo

1. Use disposable directories and synthetic UTF-8 plaintext files.
2. Compose `SQLiteStore`, `KnowledgeService`, `LocalFilesConnector`,
   `PlainTextCanonicalizer`, `LexicalIndex`, and explicit injected ACL resolver.
3. Start through `python -m kb_pipeline.cli serve DB --source-root ROOT --port 8080`.
   After `serving on`, CLI prints a **local-only** Bearer token and copyable
   `Authorization: Bearer TOKEN` guidance. Token exists only in process memory and
   expires when server stops; it is not production credential. Opening UI/static
   routes sets HttpOnly, `SameSite=Strict`, `kb_session` cookie for browser use.
   Public routes are `/v1/health`, `/v1/ready`, and static UI assets. Authenticated
   routes are `/v1/status`, `/v1/report`, `/v1/search?q=...`, and `POST /v1/answer`.
   Send either Bearer token or session cookie for demo/reference routes.
4. Verify authorized search, deny-by-default ACL, source URI, SHA-256 version,
   tombstone, revocation, incomplete-scan behavior, and restart search.
5. Rebuild index with `python -m kb_pipeline.cli index-rebuild DB` when projection
   is suspected stale.
6. Stop and discard demo data if real data or an authorization concern appears.

Protocol-demo path is local and synthetic only. Demo/reference Bearer token is
process-lifetime; never treat it as production auth. Production ignores local token
map and requires configured OIDC Bearer tokens; no production secret is printed.
External OIDC/KMS remain injected ports; no provider integration exists. Production
rejects test crypto.

## Synthetic Nango adapter experiment

Use deterministic fixtures only. Treat adapter as **EXPERIMENT only**, not production adoption. Feed emitted pairs to local ledger; acknowledge cursor only after durable ledger acceptance. Nango cache is not an archive. Do not infer deletes from incomplete snapshots. Gate 2/3 QA records **66/66 serial tests passing twice**, **15/15 targeted tests passing**, Python **3.11.12**, and compile/Node/launcher smoke passing. Production auth/KMS, atomic ledger/outbox, crash-safe checkpoint resume, concurrency convergence, observability, deployment, and real-data rehearsal remain excluded.

## Gate 5 reliability core

- SQLite opens with `WAL`, `synchronous=FULL`, foreign keys, 30-second busy timeout,
  and one process-local writer lock. Production composition requires injected OIDC and KMS ports.
- Ledger acceptance, outbox creation, raw metadata, and audit callbacks use one SQLite transaction.
- Outbox uses durable pending/claimed/applied/failed states, leases, bounded attempts, and dead letters.
- Replay validates contiguous ledger sequences and checkpoints cannot move backward or beyond ledger head.
- Gaps persist until missing revisions arrive; no-skip behavior blocks acceptance of later revisions.
- Content hashes use durable reference counts; purge state is source/document scoped and resumable by status.
- Backup/restore uses staged bundles, manifests, checksums, artifact validation, and writer quiesce.
- `/v1/ready`, `/v1/status`, and service health expose ledger, outbox, checkpoint, projection, and metrics state.

Evidence command:
`python3 -m unittest discover && python3 -m compileall -q kb_pipeline && node --check frontend/app.js`

## Gate 6 remediation: concurrency/readiness complete

Gate 6 fix validation covers synthetic local scope. Access is serialized per database;
make no multi-writer claim. Stress testing passes, and readiness gates on document
projection lag. **78 tests passed twice**; compile, Node, and git checks passed.

Earlier synthetic-local measurements in [`GATE6_SRE_RESULTS.json`](../GATE6_SRE_RESULTS.json)
cover ingest, search, replay, backup/restore, and **20/20 API readers** returning
HTTP 200. API-reader success is bounded probe evidence; it is not SQLite
concurrency evidence. Machine-specific test timing is not retained as documentation
evidence.

Qualification remains pending:

- Rerun evidence under supported Python **>=3.11**.
- Approved baseline acceptance criteria are ingest **≥100 records/s**, search **p95
  ≤100 ms**, RPO **≤24h**, and RTO **≤4h**.
- Targets remain pending a supported-runtime qualifying run; they are not proof.

Next: rerun Gate 6 under supported Python against approved targets and repeat
qualification evidence. Keep data synthetic; real-data pilot remains **NO-GO**.

### Gate 6 synthetic-local recovery rehearsal

Run bounded recovery rehearsal with:

```sh
python -m kb_pipeline.gate6_recovery
```

Validated checks are SQLite integrity, raw-artifact links, retrieval/search of
pre-backup records, and absence of post-backup records after restore. Recovery
acceptance criteria are RPO **≤24h** and RTO **≤4h**. Command output is
synthetic-local evidence only; it is not production disaster recovery, production
qualification, or pilot approval. Do not record machine-specific test timing as
documentation evidence.

Connector implementation may proceed only as local/reference scope. Production
connector adoption remains blocked on external identity/KMS, production-grade
recovery and operations, and real-data approval.

## Local/reference answer mode

Default answer behavior is deterministic abstention. Enable generated answers only
through explicit local Ollama opt-in, and require citations for every generated
answer. Keep all inputs synthetic/local; this mode grants no real-data or production
approval.

Setup flow remains generic until project integration is defined:

1. Install Ollama with its supported platform installer.
2. Start its local service with the supported Ollama start mechanism.
3. Pull an approved local model through Ollama's supported model-pull flow.
4. Start project service with the verified existing command:
   `python -m kb_pipeline.cli serve DB --source-root ROOT --port 8080`.

Verified explicit opt-in serve usage is:
`python -m kb_pipeline.cli serve DB --source-root ROOT --port 8080 --ollama-model MODEL`.
Optional flags are `--ollama-endpoint LOOPBACK_ENDPOINT` and
`--ollama-timeout SECONDS`. These flags activate only local/reference Ollama;
provider configuration and injection/data-boundary follow-up remain required.

LLM parent dependencies: citation contract (partial), provider configuration,
injection/data boundary, and groundedness evaluation.

```text
Gate 6 remediation               [██████████] Complete ✅
Supported-Python rerun + targets [░░░░░░░░░░] Next stage
Production readiness              [░░░░░░░░░░] NO-GO
```

## Gate 4 hardening

- Backup: `python -m kb_pipeline.cli backup DB BUNDLE`; staging, manifest, SHA-256 checksums, artifact-link validation. Restore validates before replacement.
- Evidence: `python -m kb_pipeline.cli pilot-evidence DB --result-json QA_RESULTS.json`; QA-owned evidence, not production certification. CLI refuses empty/default evidence.
- `/v1/ready` reports storage/replay checks; `/v1/status` reports outbox, dead letters, gaps, checkpoints, and projection lag.
- Purge accepts `source_id` or `document_id`; durable `purge_status` records running/complete/failed state. Shared hashes remain while referenced.
- Connector, canonicalizer, query, result, and runtime config limits fail closed.

### Gate 4 evidence provenance

`pilot-evidence` ingests only schema `kb-pipeline.gate4-evidence.v1` JSON. Result file
must identify suite version `0.1.0`, checked-in `tests/test_manifest.json` and its SHA-256,
manifest-derived test count, environment, capture time/source, every scenario ID and pass/fail, backup SHA-256 entries, SQLite integrity,
restore validation, interruption outcomes, purge/replay/readiness/limits/log-redaction
results, and explicit exclusions. Unknown fields and placeholder values fail closed.

## Demo incident response

- **Unexpected visibility:** stop service, revoke source, preserve synthetic reproduction,
  inspect ACL resolver and search filtering. Do not treat UI as authorization.
- **Index mismatch:** stop writes, snapshot disposable DB, run `index-rebuild`, verify
  searches. Production repair requires durable outbox/replay first.
- **API failure:** return no result details; record route/status and restart disposable
  demo. No SLO or alert exists.
- **Backup concern:** do not call current CLI backup production-safe. Preserve source DB
  and raw directory together; validate links after restore.

## Remediation order and evidence gates

1. **Authoritative ledger/outbox.** Gate: authoritative ledger/outbox design, atomic effect model, and threat model.
2. **Namespace/auth isolation.** Enforce exact `ObjectKey` boundaries, authenticated reader/admin identities, source ACLs, and encrypted payload/erasable-DEK lifecycle. Gate: identity/ACL and encryption sign-off.
3. **Purge and recovery.** Define DEK erasure and source-scoped deletion across raw, projections, backups, caches, and audit retention; prove atomic backup/restore and rehearse RPO/RTO.
4. **Replay/checkpoint recovery.** Add concurrency policy, replay, migrations, dead-letter handling, and gap-quarantine recovery.
5. **Observability, limits and operations.** Enforce limits; add metrics, logs, alerts, readiness, capacity and on-call. Reference readiness defaults to `max_projection_lag=0`, so document/search lag fails readiness. Gate: load, failure, alert, and operational rehearsal.
6. **API/UI integration and source expansion.** Provide supported composition, token, hosting, and route contract. Add only accepted connectors/MIME/attachment policy.
2. **Atomic write model.** Add single-writer/concurrency policy, transactional
   projection updates, durable outbox, replay, idempotency, migrations, dead-letter
   handling. Gate: concurrent and crash-injection tests show no lost/overexposed state.
3. **Deletion and provenance.** Define source-scoped deletion across raw, SQLite,
   FTS5, backups, caches, and audit retention; persist transformation lineage,
   freshness, citations. Gate: deletion and evidence audit passes.
4. **Purge and recovery.** Prove source-scoped purge across adapters and backups; replace copy semantics with consistent atomic backup/restore; define
   RPO/RTO and rehearse failure. Gate: clean restore plus artifact/index validation.
5. **Observability, limits and operations.** Enforce API, file, payload, storage, concurrency, and
   timeout limits. Add metrics, logs, alerts, readiness, capacity and on-call. Gate:
   load, failure, alert, and operational rehearsal passes.
6. **API/UI integration and source expansion.** Provide supported composition, token, hosting, and route contract. Add only
   explicitly accepted connectors/MIME/attachment policy. Gate: fresh-data, privacy,
   accessibility, and security acceptance.

Each gate needs owner, dated artifact, automated evidence where possible, and pilot
approval. See `docs/mvp-plan.md`.
