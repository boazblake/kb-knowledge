/* Shared visualization facts. Keep mirrored in visualization-status.json. */
window.VISUALIZATION_STATUS = Object.freeze({
  snapshot: 'b80da6c + d955b2c + edd8f23',
  decision: 'Production NO-GO',
  remediationStage: 'GREEN — local evidence',
  provider: { endpointsConfigured: false, credentialsConfigured: false, liveCalls: 0, externalConnector: false, absent: ['KMS', 'S3', 'OIDC', 'Temporal', 'OTel'] },
  suite: { run: 5, pass: 5, skipped: 0 },
  postgresValidation: { latestRun: 21, latestPass: 21, customChecksRun: 5, customChecksPass: 5, migrations: '001-005 idempotent' },
  remediation: ['Batch atomicity validated', 'Cursor comparator validated', 'Staged raw / orphan lifecycle validated', 'Outbox ownership / retry validated', 'Canonical purge namespace validated'],
  statuses: ['DONE', 'PARTIAL', 'BLOCKED', 'DEFERRED'],
  horizons: ['Prototype/reference', 'Production-shaped non-prod', 'Production qualification/release'],
  evidence: [
    'Commits: b80da6c, d955b2c, edd8f23',
    'PostgreSQL targeted authority/purge/recovery matrix: 21/21 passed',
    'Custom remediation checks: 5/5 passed', 'Migrations 001-005 idempotent',
    'Batch atomicity, cursor comparator, staged raw/orphan lifecycle, outbox ownership/retry, canonical purge namespace validated'
  ],
  missingNonProd: ['Configured non-prod OIDC/KMS/S3/Temporal/OTel endpoints', 'External connector environment'],
  missingProduction: ['Live KMS/S3/OIDC/Temporal/OTel', 'External connector', 'Production load/SLO', 'RPO/RTO', 'Recovery rehearsal', 'SEC/OPS approval'],
  next: 'External provider environment integration (OIDC/KMS/S3/Temporal/OTel) using configured non-prod endpoints only.'
});

function visualizationStatus() { return window.VISUALIZATION_STATUS; }
