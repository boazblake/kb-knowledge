/* Shared visualization facts. Keep mirrored in visualization-status.json. */
window.VISUALIZATION_STATUS = Object.freeze({
  snapshot: 'a78117c + e10de7c + current provider check',
  decision: 'Production NO-GO',
  provider: { endpointsConfigured: false, credentialsConfigured: false, liveCalls: 0, boundary: { run: 24, pass: 18, skipped: 6 } },
  suite: { run: 167, pass: 158, skipped: 9 },
  statuses: ['DONE', 'PARTIAL', 'BLOCKED', 'DEFERRED'],
  horizons: ['Prototype/reference', 'Production-shaped non-prod', 'Production qualification/release'],
  evidence: [
    'Frontend browser verification', 'PostgreSQL Nix narrow evidence', 'OIDC local JWKS packet',
    'KMS/S3 contract tests', 'Temporal/OTel contract tests', 'Purge/recovery tests',
    'Synthetic load/SLO harness'
  ],
  missingNonProd: ['OIDC provider', 'KMS', 'S3', 'Temporal', 'OTel', 'approved connector/deployment'],
  missingProduction: ['purge/recovery provider rehearsal', 'load/SLO production evidence', 'RPO/RTO', 'SEC/OPS approval'],
  next: 'Configure disposable non-production provider environment, then run end-to-end synthetic ingestion.'
});

function visualizationStatus() { return window.VISUALIZATION_STATUS; }
