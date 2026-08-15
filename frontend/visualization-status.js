/* Shared visualization facts. JSON mirror is validated before any view renders. */
window.VISUALIZATION_STATUS = Object.freeze({
  snapshot: 'Committed core evidence · fd65de8 · 2026-08-15',
  commits: { implementation: 'fd65de8', docs: 'edc9083', history: ['9be2d0b', '6a6f868'] },
  evidenceScope: 'Committed core state fd65de8; prior recorded run dated 2026-08-15; development/mock scope only',
  production_qualification: false, mode: 'MOCK / REFERENCE', decision: 'Production NO-GO',
  evidenceLabel: 'MOCK / REFERENCE — reviewed repository evidence; not production qualification',
  environment: 'Development/mock: pinned Nix and disposable PostgreSQL evidence runs',
  limitations: ['Development/mock/reference only', 'No live provider calls', 'No production qualification', 'Prior recorded run; no new test evidence claimed'],
  provider: { endpointsConfigured: false, credentialsConfigured: false, liveCalls: 0, externalConnector: false, absent: ['approved non-production provider configuration', 'real provider transport', 'credentials'] },
  evidenceRun: { runDate: '2026-08-15', nixFull: { label: 'Nix full', passed: 200, failed: 0 }, disposablePostgresqlFull: { label: 'Disposable PostgreSQL', passed: 200, failed: 0 }, targetedP4: { label: 'Targeted P4', passed: 14, failed: 0 }, labels: { label: 'Labeled scenarios', passed: 21, total: 21 } },
  suite: { name: 'Nix full', run: 200, pass: 200, failed: 0 },
  mockFlow: { status: 'PASS', description: 'Reviewed mock/reference flow; no live provider calls' },
  postgresValidation: { status: '200/0', version: 'PostgreSQL', lifecycle: 'disposable mock/reference E2E', evidence: 'Disposable PostgreSQL full suite: 200 passed / 0 failed' },
  scenarios: ['Cursor acknowledgement', 'Revision ordering', 'Upsert/update', 'Delete', 'Permission change', 'Retry classification', 'Permanent failure classification', 'Duplicate webhook', 'Incomplete snapshot safety', 'Provenance', 'Credential redaction', 'Tenant/source identity'],
  recordedChecks: ['Connector contract validated', 'Disposable PostgreSQL full suite: 200/0', 'Targeted P4 checks: 14/0', '21/21 labeled scenarios'],
  horizons: ['Prototype/reference', 'Production-shaped non-prod', 'Production qualification/release'],
  evidence: ['Committed core: fd65de8', 'History: 9be2d0b, 6a6f868', 'Docs metadata: edc9083', 'Prior recorded test run (2026-08-15) — Nix full: 200 passed / 0 failed', 'Prior recorded test run (2026-08-15) — Disposable PostgreSQL: 200 passed / 0 failed', 'Prior recorded test run (2026-08-15) — Targeted P4: 14 passed / 0 failed', 'Prior recorded test run (2026-08-15) — Labeled scenarios: 21/21', 'Development/mock/reference only; production_qualification=false; no new test evidence claimed'],
  missingNonProd: ['Approved non-production provider configuration', 'Real provider endpoints', 'Provider credentials'],
  missingProduction: ['Live provider qualification', 'Production load/SLO', 'RPO/RTO', 'Recovery rehearsal', 'SEC/OPS approval'],
  next: 'Obtain approved non-production provider configuration, then rerun live integration.',
  p4: { identity: { tenant: 'tenant-demo', source: 'reference-source', source_id: 'doc-001', authority: 'ingestion_authority' }, authoritySequence: { accepted: 42, applied: 40, state: 'stale', source: 'authority ledger; correctness source' }, outbox: { protocol_version: 'p4-envelope.v1', event_id: 'evt-reference-042', idempotency_key: 'tenant-demo/reference-source/doc-001/r42', operation: 'upsert', revision: 42, state: 'accepted' }, projection: { worker: 'PostgresProjectionWorker', projection: 'document', watermark: 40, state: 'stale', source: 'derived projection; not authority' }, fts: { state: 'pending', index: 'PostgreSQL FTS search_vector', source: 'derived projection; ACL-filtered query' }, barriers: ['fresh', 'pending', 'stale', 'blocked', 'timeout'], ingestOutcomes: ['accepted', 'duplicate', 'stale', 'gap', 'conflict', 'rejected', 'failed'], lifecycle: ['delete', 'tombstone', 'purge', 'replay'], provenance: { raw_reference: 's3://reference/raw/doc-001', content_hash: 'sha256:reference', citation: 'revision 42 + raw reference', verification: 'authority revision and ACL must agree' }, failureEvidence: { injection: 'worker failure callback observed', ledger: 'event → outbox → projection checkpoint → citation verification', recovery: 'retry/dead-letter/replay evidence is local/mock' } }
});
window.visualizationEvidence = () => window.VISUALIZATION_STATUS.evidenceRun;
window.validateVisualizationStatus = (json) => {
  const expected = window.VISUALIZATION_STATUS;
  const same = json?.commits?.implementation === expected.commits.implementation && json?.commits?.docs === expected.commits.docs && json?.evidenceScope === expected.evidenceScope && json?.production_qualification === false;
  const runs = ['nixFull', 'disposablePostgresqlFull', 'targetedP4'].every(key => json?.evidenceRun?.[key]?.passed === expected.evidenceRun[key].passed && json?.evidenceRun?.[key]?.failed === 0);
  const labels = json?.evidenceRun?.labels?.passed === 21 && json?.evidenceRun?.labels?.total === 21;
  return same && runs && labels;
};
fetch('visualization-status.json', { headers: { Accept: 'application/json' } }).then(response => response.ok ? response.json() : Promise.reject(new Error('status JSON unavailable'))).then(json => { if (!window.validateVisualizationStatus(json)) throw new Error('visualization status mismatch'); document.documentElement.dataset.statusValidated = 'true'; }).catch(() => { document.documentElement.dataset.statusValidated = 'false'; });
