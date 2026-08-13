# Demo runbook and remediation order

## Safe demo

1. Use disposable directories and synthetic UTF-8 plaintext files.
2. Compose `SQLiteStore`, `KnowledgeService`, `LocalFilesConnector`,
   `PlainTextCanonicalizer`, `LexicalIndex`, and explicit injected ACL resolver.
3. Start through `python -m kb_pipeline.cli serve DB --source-root ROOT --port 8080`;
   retain generated token locally. Routes are `/v1/health`, `/v1/ready`, `/v1/status`,
   and `/v1/search?q=...`; UI is same-origin at `/`.
4. Verify authorized search, deny-by-default ACL, source URI, SHA-256 version,
   tombstone, revocation, incomplete-scan behavior, and restart search.
5. Rebuild index with `python -m kb_pipeline.cli index-rebuild DB` when projection
   is suspected stale.
6. Stop and discard demo data if real data or an authorization concern appears.

Protocol-demo path is local and synthetic only. Loopback reader/admin identities are short-lived; never treat them as production auth. External OIDC/KMS remain injected ports; no provider integration exists. Production rejects test crypto.

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
5. **Observability, limits and operations.** Enforce limits; add metrics, logs, alerts, readiness, capacity and on-call. Gate: load, failure, alert, and operational rehearsal.
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
