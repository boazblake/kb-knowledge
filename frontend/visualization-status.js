/* Shared visualization facts. Keep mirrored in visualization-status.json. */
window.VISUALIZATION_STATUS = Object.freeze({
  snapshot: 'P4 core · 2026-08-15',
  production_qualification: false,
  mode: 'MOCK / REFERENCE',
  decision: 'Production NO-GO',
  evidenceLabel: 'MOCK / REFERENCE — not live provider or production evidence',
  environment: 'Mock/local provider environment',
  remediationStage: 'GREEN — local mock/reference evidence',
  provider: { endpointsConfigured: false, credentialsConfigured: false, liveCalls: 0, externalConnector: false, absent: ['approved non-production provider configuration', 'real provider transport', 'credentials'] },
  suite: { name: 'Full suite', run: 204, pass: 189, skipped: 15 },
  mockFlow: { status: 'PASS', description: 'Full mock flow passed previously' },
  postgresValidation: { status: 'DOCUMENTED', version: 'PostgreSQL', lifecycle: 'mock E2E', evidence: 'Mock PostgreSQL E2E documented' },
  scenarios: ['Cursor acknowledgement', 'Revision ordering', 'Upsert/update', 'Delete', 'Permission change', 'Retry classification', 'Permanent failure classification', 'Duplicate webhook', 'Incomplete snapshot safety', 'Provenance', 'Credential redaction', 'Tenant/source identity'],
  remediation: ['Connector contract validated', 'Mock PostgreSQL E2E documented', 'Full mock flow passed previously'],
  statuses: ['DONE', 'PARTIAL', 'BLOCKED', 'DEFERRED'],
  horizons: ['Prototype/reference', 'Production-shaped non-prod', 'Production qualification/release'],
  evidence: [
    'Commit: 30283d3',
    'Connector contract tests: 12/12 passed',
    'Mock PostgreSQL E2E documented; full mock flow passed previously',
    'MOCK/REFERENCE only; no real provider endpoints or credentials'
  ],
  missingNonProd: ['Approved non-production provider configuration', 'Real provider endpoints', 'Provider credentials'],
  missingProduction: ['Live provider qualification', 'Production load/SLO', 'RPO/RTO', 'Recovery rehearsal', 'SEC/OPS approval'],
  next: 'Obtain approved non-production provider configuration, then rerun live integration.',
  p4: {
    identity: { tenant: 'tenant-demo', source: 'reference-source', source_id: 'doc-001', authority: 'ingestion_authority' },
    authoritySequence: { accepted: 42, applied: 40, state: 'stale', source: 'authority ledger; correctness source' },
    outbox: { protocol_version: 'p4-envelope.v1', event_id: 'evt-reference-042', idempotency_key: 'tenant-demo/reference-source/doc-001/r42', operation: 'upsert', revision: 42, state: 'accepted' },
    projection: { worker: 'PostgresProjectionWorker', projection: 'document', watermark: 40, state: 'stale', source: 'derived projection; not authority' },
    fts: { state: 'pending', index: 'PostgreSQL FTS search_vector', source: 'derived projection; ACL-filtered query' },
    barriers: ['fresh', 'pending', 'stale', 'blocked', 'timeout'],
    ingestOutcomes: ['accepted', 'duplicate', 'stale', 'gap', 'conflict', 'rejected', 'failed'],
    lifecycle: ['delete', 'tombstone', 'purge', 'replay'],
    provenance: { raw_reference: 's3://reference/raw/doc-001', content_hash: 'sha256:reference', citation: 'revision 42 + raw reference', verification: 'authority revision and ACL must agree' },
    failureEvidence: { injection: 'worker failure callback observed', ledger: 'event → outbox → projection checkpoint → citation verification', recovery: 'retry/dead-letter/replay evidence is local/mock' }
  }
});

function visualizationStatus() { return window.VISUALIZATION_STATUS; }
