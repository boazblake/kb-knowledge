# Knowledge Pipeline

Phase 5 delivers local synthetic ingestion, durable SQLite state, SQLite FTS5 search,
protocol contracts, localhost API factory, static UI assets, and reference security
boundaries. It is
a **local protocol demo**, not a real-data pilot.

## Status

### MOCK/REFERENCE synthetic integration mode

`--mode mock` composes local RSA OIDC/JWKS, AEAD KMS, in-memory S3-compatible
storage, in-process workflow, telemetry sink, and approved synthetic connector
fixtures behind existing ports. PostgreSQL remains authority and must be a Nix
PostgreSQL DSN. Mode rejects SQLite and is explicitly **MOCK/REFERENCE ONLY**:
it rejects real/customer data and cannot qualify production. Failure injection,
rotation, retries, duplicates, and purge/no-resurrection scenarios belong in
`tests/test_mock_environment.py` and optional PostgreSQL E2E tests.

Synthetic Nango adapter: **EXPERIMENT only**, not production adoption. Immutable
Principal/AuthZ ports, fake OIDC/JWKS, fake KMS AEAD context/rotation/erasure,
production guards, and encrypted raw persistence tests are reference-only. Adapter
contract scenarios pass. Local ledger remains authority; Nango cache is not an
archive. Gate 5 QA is complete for demo/reference scope: **76 tests passed twice**,
compile, Node, and git checks pass. This is not production clearance.
Gate 2/3 QA previously recorded **66/66 serial tests pass twice**, **15/15 targeted tests pass**, Python **3.11.12**, and compile/Node/launcher
smoke checks pass. This is not production clearance.

PostgreSQL authority + encrypted raw lane composes synthetic changes through
KMS-bound client-side encryption, S3-compatible storage, and PostgreSQL metadata,
idempotency, audit, outbox, tombstone, and checkpoint transactions. Persisted raw
read/decrypt/hash verification and tenant/context fail-closed checks are covered by
local adapter contracts. PostgreSQL runtime evidence requires `P3_POSTGRES_DSN`;
AWS KMS/S3 live evidence is absent.

Gate 6 SRE evidence is captured in [`GATE6_SRE_RESULTS.json`](GATE6_SRE_RESULTS.json),
but production qualification failed. Synthetic-local measurements include ingest,
search, replay, backup/restore, and bounded API-reader checks; machine-specific test
timing is not retained as documentation evidence.
Gate 6 defects fixed in reference path: SQLite uses serialized per-database access
for shared connections, bounded busy timeout, WAL, foreign keys, and full sync;
readiness now fails when document/search projection lag exceeds configured
`max_projection_lag` (default **0**). Concurrent evidence remains synthetic-only
and does not claim multi-writer support or production readiness.

Approved baseline acceptance criteria are ingest **≥100 records/s**, search **p95
≤100 ms**, RPO **≤24h**, and RTO **≤4h**. These targets await a supported-runtime
qualifying run; they are not proof. Synthetic-local limits remain in force, and the
real-data pilot remains **NO-GO**.

Gate 6 synthetic-local recovery rehearsal:

```sh
python -m kb_pipeline.gate6_recovery
```

It validates SQLite integrity, raw-artifact links, pre-backup retrieval, and
post-backup absence against RPO **≤24h** and RTO **≤4h**. This is not production
disaster recovery or pilot approval; machine-specific test timing is not evidence.

```text
Gate 5  Reliability + security [██████████] Validated reference ✅
Gate 6  SRE evidence          [████░░░░░░] Failed qualification ❌
Next   Fix, rerun, define targets, repeat evidence [░░░░░░░░░░]
```

| Area | Status |
|---|---|
| Local file scan and UTF-8 canonicalization | Implemented |
| ACL-filtered lexical search | Implemented; injected test/demo policy |
| SQLite/WAL documents, raw artifacts, tombstones, revocations, checkpoints, audit | Implemented reference path |
| Principal/AuthZ and OIDC/KMS boundaries | Reference ports; fake-only adapters |
| PostgreSQL authority + encrypted S3 raw path | Synthetic contract; live provider evidence unavailable |
| FTS5 projection and restart rebuild | Implemented |
| API `/v1/*` routes | Library factory; no service launcher |
| Static UI | Shell only; no supported hosting/composition path |
| Email, MIME, attachments, vectors, relationships, MCP | Deferred |
| OpenAI answer adapter | Opt-in only; sends bounded query/evidence to cloud; never use sensitive data |
| Real-data pilot | **NO-GO** |

QA/BDD/SRE evidence uses checked-in test-manifest provenance. Tests cover narrow fixture
behavior; they do not establish security, availability, recovery, concurrency, or
pilot readiness.

## Stable protocol spine

`IdentityNamespace`, `ObjectKey`, `Envelope`, `CanonicalChange`, `PermissionState`,
`ProvenanceLink`, `Ledger`, `KnowledgeStore`, `Projection`, `Query`, and
`CompositionManifest` define provider-neutral boundaries. Exact `ObjectKey` is
`(provider, tenant, connector, source_instance, object_id)`. `KnowledgeEngine` appends
changes, applies state/projections, and replays from reference ledger. Duplicate
delivery is idempotent; conflicting same-revision payloads are quarantined.

Reference adapters reused by demo composition: `LocalFilesConnector`,
`PlainTextCanonicalizer`, `SQLiteStore`, `RelationalReferenceLedger`,
`CurrentStateStore`, state/document/relationship/lexical projections, `LexicalIndex`,
and injected ACL/audit implementations. These are reference implementations, not
production guarantees.

## Documentation

- [Reproducible Nix environment and QA commands](docs/nix-environment.md)
- [Architecture and target-node mapping](docs/architecture.md)
- [Pilot readiness and NO-GO blockers](docs/pilot-readiness.md)
- [Demo runbook and remediation order](docs/runbook.md)
- [MVP plan and acceptance gates](docs/mvp-plan.md)
- [Protocol MVP plan](docs/protocol-mvp-plan.md)
- [Conceptual target architecture](BII.md)

## Supported-runtime SLO harness

Run synthetic local measurements with pinned Python 3.11:

```sh
nix run .#slo-harness -- --records 200 --searches 200 --concurrency 4 --warmup 20 --output slo-evidence.json
```

Output labels `synthetic-local-simulated`, records commit/runtime/topology/workload/timestamps,
and compares approved defaults: availability 99.9%, search p95 ≤100 ms, ingest ≥100 records/s,
freshness, purge SLA. Readiness fails closed when authority or freshness dependencies are stale.
No real data, deployment, OpenSearch, UI, or production qualification.

## Remaining production gaps

Real OIDC/KMS integrations; persisted-artifact decryption read path; canonical ledger
encryption migration; deployment and operations; load/concurrency evidence; measured
RPO/RTO; accepted external connectors/projections; observability and on-call rehearsal.

Next actions: rerun Gate 6 under supported Python **>=3.11** against approved baseline
acceptance criteria, then repeat production qualification. Targets are not proof until
a supported-runtime qualifying run exists.

Connector implementation may proceed only as local/reference scope. Production
connector adoption remains blocked on external identity/KMS, production-grade
recovery and operations, and real-data approval.

## Local/reference answer mode

Answer mode defaults to deterministic abstention: search/retrieval may return
evidence, but no generated answer is emitted unless an explicit local Ollama opt-in
is supplied. Any generated answer requires citations to retrieved evidence. This is
local/reference behavior only; it is not real-data or production approval.

Ollama setup is intentionally generic pending project wiring: install Ollama using
its supported platform installer, start its local service using its supported start
mechanism, and pull an approved local model using Ollama's model-pull flow. The
project serve command is currently:

```sh
python -m kb_pipeline.cli serve DB --source-root ROOT --port 8080
```

Verified explicit opt-in serve usage is:

```sh
python -m kb_pipeline.cli serve DB --source-root ROOT --port 8080 --ollama-model MODEL
```

Optional serve flags are `--ollama-endpoint LOOPBACK_ENDPOINT` and
`--ollama-timeout SECONDS`. Ollama endpoint must remain loopback; flags activate
local/reference behavior only.

LLM parent dependencies remain: citation contract (partial), provider configuration,
injection/data boundary, and groundedness evaluation.

## Local serve authentication

After `serving on`, demo and mock modes print a local-only Bearer token plus
`Authorization: Bearer TOKEN` usage. Token stays in memory and is valid until that
server process stops. It is never a production credential. Opening local UI/static
assets sets an HttpOnly `kb_session` cookie; API clients may use either cookie or
Bearer token in demo/reference mode. `/v1/health`, `/v1/ready`, and static assets are
public. `/v1/status`, `/v1/report`, `/v1/search`, and `POST /v1/answer` require auth.
Production prints no local token and accepts only configured OIDC Bearer auth.

## Explicit real-data NO-GO blockers

Ledger authority/outbox; namespace/auth isolation; replay/checkpoints; purge/recovery;
API/UI integration; observability. Also unresolved: production identity, encryption,
concurrency control, atomic backup/restore, enforced limits, and complete
provenance/freshness/citation evidence.

Adapter limitations remain around revisions, raw retention, permissions, replay,
purge, and credentials. Concurrent fixed-port test execution has known **P2
collision**.
