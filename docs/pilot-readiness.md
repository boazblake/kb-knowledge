# Pilot readiness

## Decision

**NO-GO.** Demo path works against synthetic local plaintext files. Do not load
confidential, customer, regulated, email, attachment, or credential data.

**Current stage:** Nix environment reproducibility complete ✅
**Next stage:** Supported-runtime load, RPO, and RTO evidence

## Approved baseline acceptance criteria

Approved baseline targets: ingest **≥100 records/s**; search **p95 ≤100 ms**;
RPO **≤24h**; RTO **≤4h**. These targets are acceptance criteria pending a
supported-runtime qualifying run, not proof or production certification.

```text
Gate 1  Security and authority       [░░░░░░░░░░]  Unclosed
Gate 2  Durability and replay        [██████████]  Reference evidence complete
Gate 3  Deletion and recovery        [██████████]  Reference evidence complete
Gate 4  Operations and product QA    [██████░░░░]  Fixture evidence
Gate 5  Reliability core             [██████████]  Validated, fixture/reference ✅
Gate 6  Concurrency/readiness fix    [██████████] Complete ✅
Nix     Reproducible environment     [██████████] Complete ✅
Next    Supported load + RPO/RTO     [░░░░░░░░░░] Required
Prod    Production readiness         [░░░░░░░░░░] NO-GO
```

## What current evidence proves

Gate 4 adds durable purge status, shared-artifact-safe purge, staged/checksummed backup bundles, readiness and replay health, redacted request logs, bounded configuration, and QA evidence output. This remains fixture evidence only; no production claims.

Gate 2 and Gate 3 evidence is complete for demo/reference scope. `GATE2_QA_RESULTS.json` and `GATE3_QA_RESULTS.json` record Python **3.11.12**, **66/66 serial tests passing twice**, **15/15 targeted tests passing**, compile/Node/launcher smoke passing, and dynamic-port test isolation. The suite uses checked-in test-manifest provenance covering contracts, ACL denial,
tombstones, retry behavior, revocation boundaries, SQLite restart indexing, FTS5,
CLI artifact-link checks, incomplete scans, and UI safety. This proves narrow behavior
under test fixtures only; evidence does not clear production readiness.

Gate 5 validation records **76 tests passed twice**, **six new QA scenarios passed**,
compile, Node, and git checks passed, plus SHA-256 checksums, SQLite integrity,
restore/interruption outcomes, and injected-failure outcomes in
[`GATE5_QA_RESULTS.json`](../GATE5_QA_RESULTS.json). Coverage is unavailable;
these results are reference evidence, not production certification.

Gate 6 evidence is recorded in [`GATE6_SRE_RESULTS.json`](../GATE6_SRE_RESULTS.json).
Synthetic-local measurements cover ingest, search, replay, backup/restore, and a
bounded API-reader check. Machine-specific test timing is not retained as
documentation evidence.
These numbers do not establish production capacity or SLO compliance.
They are synthetic-local measurements only and must not be treated as qualification
evidence until rerun in a supported runtime.

Gate 6 remediation passes synthetic validation: access is serialized per database,
no multi-writer claim is made, stress testing passes, and document projection lag
gates readiness. **78 tests passed twice**; compile, Node, and git checks passed.
The reproducible Nix environment is complete: checked-in `flake.nix` and `flake.lock`
pin Python **3.11.11**, Node **22.16**, and SQLite **3.46**. `nix flake check`,
`nix run .#check`, `nix run .#benchmark`, and `nix run .#evidence` validate the
environment and QA tooling. Production qualification remains pending: supported-runtime
load evidence and numeric SLO, RPO, and RTO targets. `.#benchmark` is QA preflight
only; it is not production SRE evidence.

Gate 6 synthetic-local recovery rehearsal command:

```sh
python -m kb_pipeline.gate6_recovery
```

Rehearsal checks SQLite integrity, raw-artifact links, retrieval/search of records
present before backup, and absence of records added after backup. Recovery targets
are RPO **≤24h** and RTO **≤4h**. This is not production disaster recovery or pilot
approval; machine-specific test timing is not retained as documentation evidence.

## Reference evidence versus production blockers

**Reference evidence ✅:** immutable Principal/AuthZ ports, fake OIDC/JWKS validation,
fake KMS AEAD envelopes with context binding, rotation and erasure, production guards,
encrypted raw persistence tests, transactional ledger/outbox, replay and gap controls,
artifact-reference safety, resumable purge, staged backup validation, readiness,
metrics, bounded limits, and recorded failure outcomes.

**Production blockers ❌:** real OIDC/KMS integrations and tenant boundaries;
decryption read path; canonical ledger encryption migration; deployment/operations;
load/concurrency and measured RPO/RTO; accepted external connectors and production
rehearsal and approval; coverage report unavailable.

Connector implementation can proceed only as local/reference scope. Production
connector adoption remains blocked on external identity/KMS, production-grade
recovery and operations, and real-data approval.

## Local/reference answer mode

Answer mode must abstain deterministically by default. Explicit local Ollama opt-in
is required for generated answers, and citations are required for every answer.
This remains local/reference behavior only: no real-data or production approval.

Use generic platform-supported placeholders for Ollama install, local-service start,
and model pull. The verified project serve command is
`python -m kb_pipeline.cli serve DB --source-root ROOT --port 8080 --ollama-model MODEL`.
Optional flags are `--ollama-endpoint LOOPBACK_ENDPOINT` and
`--ollama-timeout SECONDS`; these activate only local/reference behavior.

Remaining LLM parent dependencies: citation contract (partial), provider config,
injection/data boundary, and groundedness evaluation.

## Explicit real-data pilot blockers

1. **Atomic ledger/outbox:** no production-authoritative atomic workflow coordinates raw, canonical, projection, and audit effects.
2. **Production auth/KMS:** immutable ports and fake-only validators/envelopes exist,
but real OIDC, production tenant boundaries, authenticated identity, source ACL
enforcement, and KMS evidence do not.
3. **Replay/checkpoints:** reference methods exist, but crash-safe checkpoint resume is excluded.
4. **Purge/recovery:** local reference purge exists, but cross-adapter deletion, atomic backup/restore, RPO/RTO, and rehearsal do not.
5. **Deployment:** local launcher smoke passes, but supported production hosting, deployment, and composition remain absent.
6. **Encryption read path:** encrypted raw persistence tests pass, but persisted-artifact decryption reads and canonical ledger encryption migration remain absent.
7. **Observability:** no production metrics, tracing, alerting, capacity, or on-call evidence.
8. **External connectors/projections:** accepted non-local connectors and production projection integrations/purge lack evidence. Nango remains experiment only; its cache is not an archive.
9. **Concurrency convergence:** serialized per-database access and stress validation pass; no multi-writer support is claimed. Production-scale convergence remains unproven.
10. **Real-data rehearsal:** no real-data rehearsal or pilot approval exists; real-data remains **NO-GO**.
11. **Coverage:** coverage report unavailable; 76-test execution cannot be treated as coverage evidence.
12. **Gate 6 qualification gaps:** supported-runtime load evidence and numeric SLO/RPO/RTO comparison remain pending. The benchmark app is QA preflight only, not production SRE evidence.

## Additional gaps

1. **Identity and authorization:** bearer token map is process-local; no authenticated
   user identity, SSO, tenant isolation, source-enforced ACL, or admin control.
2. **Encryption and secrets:** plaintext raw artifacts and SQLite files; no encryption,
   key management, secret handling, or secure deployment boundary.
3. **Consistency and concurrency:** serialized per-database access is validated, but
   no multi-writer support is claimed; document, FTS5, audit, and raw writes lack one
   production-authoritative atomic workflow.
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

## Exact next action

Run supported-runtime load testing and record numeric SLO/RPO/RTO evidence inside
the pinned Nix environment against approved baseline acceptance criteria: ingest
**≥100 records/s**, search **p95 ≤100 ms**, RPO **≤24h**, and RTO **≤4h**. Keep
inputs synthetic; these targets are not proof until qualifying evidence exists, and
real-data pilot remains **NO-GO** until approval.
