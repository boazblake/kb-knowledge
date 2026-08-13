# Pilot readiness

## Decision

**NO-GO.** Demo path works against synthetic local plaintext files. Do not load
confidential, customer, regulated, email, attachment, or credential data.

## What current evidence proves

Gate 4 adds durable purge status, shared-artifact-safe purge, staged/checksummed backup bundles, readiness and replay health, redacted request logs, bounded configuration, and QA evidence output. This remains fixture evidence only; no production claims.

The reported Phase 5 QA/BDD/SRE suite uses checked-in test-manifest provenance covering contracts, ACL denial,
tombstones, retry behavior, revocation boundaries, SQLite restart indexing, FTS5,
CLI artifact-link checks, incomplete scans, and UI safety. This proves narrow behavior
under test fixtures only.

## Explicit real-data pilot blockers

1. **Ledger authority/outbox:** no authoritative ledger for all effects and no durable outbox coordinating raw, canonical, projection, and audit writes.
2. **Namespace/auth isolation:** protocol namespaces exist, but production tenant boundaries, authenticated identity, and source ACL enforcement do not.
3. **Replay/checkpoints:** reference methods exist, but crash-safe bounded resume and failure-injection evidence do not.
4. **Purge/recovery:** local reference purge exists, but cross-adapter deletion, atomic backup/restore, RPO/RTO, and rehearsal do not.
5. **API/UI integration:** API is a factory without launcher/deployment; UI has no supported token, hosting, or composition path.
6. **Observability:** no readiness, metrics, tracing, alerting, log policy, capacity evidence, or on-call procedure.

## Additional gaps

1. **Identity and authorization:** bearer token map is process-local; no authenticated
   user identity, SSO, tenant isolation, source-enforced ACL, or admin control.
2. **Encryption and secrets:** plaintext raw artifacts and SQLite files; no encryption,
   key management, secret handling, or secure deployment boundary.
3. **Consistency and concurrency:** no serialized multi-writer contract; document,
   FTS5, audit, and raw writes lack one atomic workflow; no durable outbox/replay.
4. **Recovery:** CLI copy/restore is not atomic or lock-aware; no backup consistency
   proof, restore rehearsal, RPO/RTO, disaster recovery, or failure-injection evidence.
5. **Limits and abuse controls:** local scan/parser limits exist, but no reviewed,
   enforced API/request/storage quotas, rate limiting, or capacity model.
6. **Monitoring and operations:** no deployment service, readiness model, metrics,
   alerts, tracing, log retention, on-call, or incident workflow.
7. **Source-scoped deletion:** local-file reconciliation and document tombstones exist,
   but end-to-end deletion of raw artifacts, projections, backups, caches, and audit
   retention semantics is not specified or proven.
8. **Provenance and evidence:** hit contains URI and payload hash only; no complete
   transformation chain, freshness policy, formal citations, or evidence bundle.
9. **Scope and UI integration:** only local plaintext is supported; UI route does not
   match API route; no email/MIME/attachment path.

## Exit gate

Pilot owner approves only after [MVP acceptance gates](mvp-plan.md) pass with named
owners, automated tests, security/privacy review, recovery rehearsal, operational
rehearsal, and evidence recorded. Test count alone cannot change NO-GO.
