# Knowledge Pipeline

Phase 5 delivers local synthetic plaintext ingestion, durable SQLite state, SQLite
FTS5 search, protocol contracts, localhost API factory, and static UI assets. It is
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

| Area | Status |
|---|---|
| Local file scan and UTF-8 canonicalization | Implemented |
| ACL-filtered lexical search | Implemented; injected test/demo policy |
| SQLite/WAL documents, raw artifacts, tombstones, revocations, checkpoints, audit | Implemented reference path |
| FTS5 projection and restart rebuild | Implemented |
| API `/v1/*` routes | Library factory; no service launcher |
| Static UI | Shell only; no supported hosting/composition path |
| Email, MIME, attachments, vectors, relationships, LLM, MCP | Deferred |
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

- [Architecture and target-node mapping](docs/architecture.md)
- [Pilot readiness and NO-GO blockers](docs/pilot-readiness.md)
- [Demo runbook and remediation order](docs/runbook.md)
- [MVP plan and acceptance gates](docs/mvp-plan.md)
- [Protocol MVP plan](docs/protocol-mvp-plan.md)
- [Conceptual target architecture](BII.md)

## Explicit real-data NO-GO blockers

Ledger authority/outbox; namespace/auth isolation; replay/checkpoints; purge/recovery;
API/UI integration; observability. Also unresolved: production identity, encryption,
concurrency control, atomic backup/restore, enforced limits, and complete
provenance/freshness/citation evidence.
## Supported-runtime SLO harness

Run synthetic local measurements with pinned Python 3.11:

```sh
nix run .#slo-harness -- --records 200 --searches 200 --concurrency 4 --warmup 20 --output slo-evidence.json
```

Output labels `synthetic-local-simulated`, records commit/runtime/topology/workload/timestamps,
and compares approved defaults: availability 99.9%, search p95 ≤100 ms, ingest ≥100 records/s,
freshness, purge SLA. Readiness fails closed when authority or freshness dependencies are stale.
