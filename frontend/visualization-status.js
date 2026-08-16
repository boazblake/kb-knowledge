/* Shared, read-only reference facts. Mirror renders first so file:// never blanks. */
(() => {
  'use strict';
  const status = {
    snapshot: 'Authoritative SRE snapshot · HEAD 314eb94 · tested ancestor 397911e01029c8e626d98b9661263f8a2f7ff00c · 2026-08-15',
    commits: { head: '314eb94', tested: '397911e01029c8e626d98b9661263f8a2f7ff00c', testedIsAncestor: true },
    migrations: { applied: [1, 2, 3, 4, 5, 6, 7], freshRun: '1..7', secondRun: 'no-op' },
    evidenceScope: 'Mock providers/reference evidence only; no live provider qualification.',
    production_qualification: false, mode: 'MOCK / REFERENCE', decision: 'Production NO-GO',
    statuses: { bdd: 'PASS', sre: 'CONDITIONAL DEVELOPER GO', qa: 'SCRIPTED QA ONLY', production: 'NO-GO' },
    dirtyWorktree: 'Dirty only due excluded frontend/repository-metrics.json; excluded from evidence.',
    evidenceRun: { runDate: '2026-08-15', nix: { label: 'Nix suite · no PostgreSQL DSN', passed: 221, skipped: 34, failed: 0 }, disposablePostgresql: { label: 'Fresh disposable PostgreSQL suite', passed: 221, skipped: 0, failed: 0 }, frontendBdd: { label: 'Frontend BDD', passed: 9, skipped: 0, failed: 0 } },
    next: 'Refresh evidence/runbook metadata, then scripted test-operator handoff; production gates remain deferred.',
    horizons: ['Prototype/reference', 'Production-shaped non-prod', 'Production qualification/release'],
    limitations: ['Mock providers/reference only', 'No live provider qualification', 'Read-only/observational surface', 'Production gates deferred'], readOnly: true,
    provider: { liveCalls: 0, qualification: 'not performed' },
    scenarios: ['Cursor acknowledgement', 'Revision ordering', 'Upsert/update', 'Delete', 'Permission change', 'Retry classification', 'Permanent failure classification', 'Duplicate webhook', 'Incomplete snapshot safety', 'Provenance', 'Credential redaction', 'Tenant/source identity'],
    p4: { identity: { tenant: 'tenant-demo', source: 'reference-source', source_id: 'doc-001', authority: 'ingestion_authority' }, authoritySequence: { accepted: 42, applied: 40, state: 'stale', source: 'authority ledger; correctness source' }, outbox: { protocol_version: 'p4-envelope.v1', event_id: 'evt-reference-042', idempotency_key: 'tenant-demo/reference-source/doc-001/r42', operation: 'upsert', revision: 42, state: 'accepted' }, projection: { worker: 'PostgresProjectionWorker', projection: 'document', watermark: 40, state: 'stale', source: 'derived projection; not authority' }, fts: { state: 'pending', index: 'PostgreSQL FTS search_vector', source: 'derived projection; ACL-filtered query' }, barriers: ['fresh', 'pending', 'stale', 'blocked', 'timeout'], ingestOutcomes: ['accepted', 'duplicate', 'stale', 'gap', 'conflict', 'rejected', 'failed'], lifecycle: ['delete', 'tombstone', 'purge', 'replay'], provenance: { raw_reference: 's3://reference/raw/doc-001', content_hash: 'sha256:reference', citation: 'revision 42 + raw reference', verification: 'authority revision and ACL must agree' }, failureEvidence: { injection: 'worker failure callback observed', ledger: 'event → outbox → projection checkpoint → citation verification', recovery: 'retry/dead-letter/replay evidence is local/mock' } }
  };
  window.VISUALIZATION_STATUS = Object.freeze(status);
  window.visualizationEvidence = () => status.evidenceRun;
  window.visualizationRunLabel = run => `${run.passed} passed / ${run.skipped ?? 0} skipped / ${run.failed} failed`;
  window.validateVisualizationStatus = json => json?.commits?.head === status.commits.head && json?.commits?.tested === status.commits.tested && json?.production_qualification === false && JSON.stringify(json?.migrations?.applied) === JSON.stringify(status.migrations.applied) && json?.evidenceRun?.nix?.passed === 221 && json?.evidenceRun?.nix?.skipped === 34 && json?.evidenceRun?.disposablePostgresql?.passed === 221 && json?.evidenceRun?.frontendBdd?.passed === 9;
  window.renderVisualizationStatus = (message = '') => {
    let el = document.querySelector('#shared-status');
    if (!el) { el = document.createElement('aside'); el.id = 'shared-status'; el.className = 'shared-status'; el.setAttribute('aria-label', 'Authoritative SRE snapshot'); document.querySelector('main')?.prepend(el); }
    el.innerHTML = `<strong>${status.decision}</strong><span>HEAD <code>${status.commits.head}</code> · tested ancestor <code>${status.commits.tested}</code> · migrations ${status.migrations.freshRun} (second run ${status.migrations.secondRun})</span><span>BDD ${status.statuses.bdd} · SRE ${status.statuses.sre} · test-operator ${status.statuses.qa} · production ${status.statuses.production}</span><span>${status.dirtyWorktree}</span>${message ? `<span class="status-error" role="alert">${message}</span>` : ''}`;
  };
  window.renderVisualizationStatus();
  fetch('visualization-status.json', { headers: { Accept: 'application/json' } }).then(response => response.ok ? response.json() : Promise.reject(new Error(`status HTTP ${response.status}`))).then(json => { if (!window.validateVisualizationStatus(json)) throw new Error('status snapshot mismatch'); document.documentElement.dataset.statusValidated = 'true'; }).catch(error => { document.documentElement.dataset.statusValidated = 'false'; window.renderVisualizationStatus(`Live status mirror unavailable (${error.message}); showing embedded reference snapshot.`); });
})();
