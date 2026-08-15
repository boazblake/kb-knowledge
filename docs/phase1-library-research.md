# Phase 1 Library Research

```text
+--------------------------------------------------------------+
| STATUS: RESEARCH COMPLETE                         PROD: NO-GO |
| DONE: component options; contracts; PostgreSQL authority      |
| OPEN: license/deployment/confidence matrix; OpenSearch trigger|
| BLOCKERS: identity/KMS; authority; purge; recovery evidence   |
| NEXT: validate pgvector+PostgreSQL FTS; define scale trigger  |
+--------------------------------------------------------------+
```

## Research record standard

- Full findings remain below; this record adds status and current-direction context without deleting substantive material.
- Record metadata must name agent role, date, source or source set, and validation owner.
- Label agent findings separately from recommendations. Article claims, where present, must remain separate from recommendations and repository facts.
- Keep unresolved decisions explicit. No silent resolution, inference, or acceptance approval is allowed.

### Current locked direction

Use **pgvector plus PostgreSQL full-text search** for initial retrieval. Keep PostgreSQL authoritative. Reconsider **OpenSearch later** only after a recorded trigger such as measured scale, query latency, operational isolation, or retrieval-feature limits.

> **Provenance:** Web-librarian agent; Phase 1; 2026-08-15; validation owner: Parent.
>
> **Editorial note:** **Agent finding** preserves research conclusions. Tables, grouping, and explicit recovery limits are editorial organization. Alternatives are not silently rejected.

## Comparison and recommendation table

| Capability | Recommended default | Alternative / boundary | Source URLs |
|---|---|---|---|
| Document parsing | [Docling](https://github.com/docling-project/docling) behind chunk adapter | [Unstructured](https://docs.unstructured.io/) where supported formats or deployment model fit better | [Docling GitHub](https://github.com/docling-project/docling); [Unstructured docs](https://docs.unstructured.io/) |
| App OAuth and sync | [Nango](https://docs.nango.dev/) | [Airbyte](https://docs.airbyte.com/) for warehouse/ELT workloads | [Nango docs](https://docs.nango.dev/); [Nango GitHub](https://github.com/NangoHQ/nango); [Airbyte docs](https://docs.airbyte.com/) |
| Vector retrieval | [pgvector](https://github.com/pgvector/pgvector) by default | [Qdrant](https://qdrant.tech/documentation/) at vector scale | [pgvector GitHub](https://github.com/pgvector/pgvector); [Qdrant docs](https://qdrant.tech/documentation/) |
| Durable workflows | [Temporal](https://docs.temporal.io/) | [Celery](https://docs.celeryq.dev/) for short tasks | [Temporal docs](https://docs.temporal.io/); [Celery docs](https://docs.celeryq.dev/) |
| OIDC | Managed OIDC provider | [Keycloak](https://www.keycloak.org/documentation) when self-hosting is required | [Keycloak docs](https://www.keycloak.org/documentation) |
| Runtime authorization | [Cedar](https://www.cedarpolicy.com/en) | [OPA](https://www.openpolicyagent.org/docs) when platform-wide policy integration is required | [Cedar](https://www.cedarpolicy.com/en); [OPA docs](https://www.openpolicyagent.org/docs) |
| Telemetry | [OpenTelemetry](https://opentelemetry.io/docs/) + [Prometheus](https://prometheus.io/docs/) + [Grafana](https://grafana.com/docs/) | Deployment-managed equivalents only when contracts remain compatible | [OpenTelemetry docs](https://opentelemetry.io/docs/); [Prometheus docs](https://prometheus.io/docs/); [Grafana docs](https://grafana.com/docs/) |
| Authority | [PostgreSQL](https://www.postgresql.org/docs/) | None proposed; authority remains transactional | [PostgreSQL docs](https://www.postgresql.org/docs/) |

## Agent findings by capability

### Parsing

Use Docling behind chunk adapter. Parser output must expose stable document identity, source provenance, content, metadata, and chunk boundaries. Parser choice must not leak into policy or query contracts. Unstructured remains alternative when format coverage or deployment constraints outweigh Docling preference.

### Connectors

Use Nango for application OAuth and synchronization. Use Airbyte for warehouse and ELT integration, not automatic replacement for app-sync connector. Integration contract must define identity, cursoring, retries, rate limits, token handling, deletion signals, and provenance.

### Retrieval — unresolved

pgvector is recommended default because it keeps vector data near Postgres authority and reduces initial operational surface. Qdrant is appropriate at vector scale. This is not final search decision: architect recommends **OpenSearch as initial target** for hybrid retrieval, while product manager recommends **pgvector default**. Preserve conflict for Phase 2.

**Current locked direction.** Initial retrieval uses **pgvector plus PostgreSQL full-text search**. OpenSearch is deferred until a measured scale, latency, operational-isolation, or retrieval-feature trigger is recorded. Historical recommendations remain preserved; licensing, deployment, and confidence details remain unresolved.

### Workflows

Temporal is preferred for durable, retryable, long-running ingestion and purge workflows. Celery fits short tasks but does not become default merely because it is simpler. Integration must make idempotency, retry policy, cancellation, timeout, and failure ownership explicit.

### Identity and policy

Prefer managed OIDC. Keycloak is self-hosted alternative. Use Cedar for runtime authorization and OPA where policy must integrate across platform controls. Neither choice removes Python semantic policy and deny-by-default enforcement.

### Observability and authority

Use OTel instrumentation, Prometheus metrics, and Grafana dashboards. PostgreSQL remains system of record for accepted knowledge state and policy-relevant metadata. Derived indexes must be rebuildable and must not become authority.

## Integration contract

**Agent finding.** Every adapter remains behind stable Python contracts. Contracts must preserve:

- tenant/source ACL semantics and deny-by-default behavior;
- stable identity and cursoring;
- retries, rate limits, idempotency, cancellation, and timeout behavior;
- token handling and deletion signals;
- source/document provenance, content, metadata, and chunk boundaries;
- purge behavior and evidence;
- failure ownership and replayability;
- authority boundary: PostgreSQL is transactional system of record; indexes are derived.

## Licensing, deployment, and confidence

**Agent finding.** Evaluate each component against license, deployment model, operational ownership, scale, security, upgrade path, and contract fit. Do not adopt library when it cannot preserve tenant/source ACL semantics, provenance, purge behavior, retries, or evidence.

The recovered Phase 1 artifact contains no per-library license matrix, deployment matrix, or confidence score. Those values are not invented here. Source links above are exact URLs preserved from available findings.

## Do-not-adopt cases

**Agent finding.** Do not adopt component when it breaks stable Python contracts or cannot preserve ACL semantics, provenance, purge behavior, retry/evidence requirements, or authority boundaries. Do not use Airbyte as automatic app-sync replacement. Do not treat Celery as durable-workflow default merely because it is simpler. Do not make derived index authoritative.

## Final research default

**Agent finding.** Postgres authority; Docling plus chunk adapter; Nango for app sync; Airbyte only for warehouse/ELT; pgvector default pending Phase 2 search decision; Temporal for durable workflows; managed OIDC; Cedar runtime policy; OTel, Prometheus, and Grafana. Alternatives remain documented rather than rejected.

## Source inventory

Official sources preserved: Docling GitHub, Unstructured docs, Nango docs/GitHub, Airbyte docs, Qdrant docs, pgvector GitHub, Temporal docs, Celery docs, Keycloak docs, Cedar site, OPA docs, OTel docs, Prometheus docs, Grafana docs, and PostgreSQL docs. URLs appear in comparison table.

## Recovery limits

Full web-librarian terminal transcript, including any comparison columns or per-source confidence/licensing/deployment notes not present in recovered artifact, was unavailable in workspace context. Missing values remain explicitly marked; no recommendation or contradiction was silently resolved.
