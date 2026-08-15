const S = window.VISUALIZATION_STATUS || (() => { const request = new XMLHttpRequest(); request.open('GET', 'visualization-status.json', false); request.send(); const data = JSON.parse(request.responseText); if (!data.commits || data.production_qualification !== false) throw new Error('visualization status mismatch'); return data; })();
const E = S.evidenceRun;
document.querySelector('.evidence-note p').textContent = `Reviewed evidence: implementation ${S.commits.implementation}; docs ${S.commits.docs}; Nix full ${E.nixFull.passed}/${E.nixFull.failed}; disposable PostgreSQL ${E.disposablePostgresqlFull.passed}/${E.disposablePostgresqlFull.failed}; targeted P4 ${E.targetedP4.passed}/${E.targetedP4.failed}; labeled scenarios ${E.labels.passed}/${E.labels.total}. Production qualification=false.`;
const stages = [
  ['Input','DONE','DONE','PARTIAL','Frontend browser verification; local file scan.','Approved source contract absent.'],
  ['Connector','PARTIAL','DEFERRED','PARTIAL',`Reviewed evidence: Nix ${E.nixFull.passed}/${E.nixFull.failed}; zero live calls.`,'Approved non-production provider configuration, endpoints, and credentials absent.'],
  ['Canonical Model','DONE','DEFERRED','PARTIAL','Protocol, idempotency, quarantine fixtures.','Real-data qualification absent.'],
  ['Knowledge Engine','PARTIAL','BLOCKED','DONE',`Disposable PostgreSQL ${E.disposablePostgresqlFull.passed}/${E.disposablePostgresqlFull.failed}; targeted P4 ${E.targetedP4.passed}/${E.targetedP4.failed}; labels ${E.labels.passed}/${E.labels.total}.`,'KMS/S3/Temporal/OTel live evidence and production RPO/RTO absent.'],
  ['Output','PARTIAL','BLOCKED','PARTIAL','Frontend browser verification; local search/report.','Approved deployment and production SLO absent.'],
  ['Identity & Access','PARTIAL','BLOCKED','PARTIAL','OIDC local JWKS packet.','Live OIDC provider and tenant evidence absent.'],
  ['Observability','PARTIAL','BLOCKED','PARTIAL','Local contract evidence only.','Live OTel, alerts, on-call, production load/SLO absent.'],
  ['Backup & Resilience','PARTIAL','BLOCKED','PARTIAL','Purge/recovery tests; synthetic-local only.','Provider rehearsal and RPO/RTO absent.']
].map(([label, prototype, adoption, evidence, tests, blockers]) => ({label, prototype, adoption, evidence, tests, blockers}));
const statusClass = status => status.toLowerCase();
const grid = document.querySelector('#stage-grid');
const done = stages.filter(stage => stage.evidence === 'DONE').length;
const denominator = 15;
document.querySelector('#completion-value').textContent = `${Math.round(done / denominator * 100)}%`;
document.querySelector('#completion-fill').style.width = `${done / denominator * 100}%`;
document.querySelector('#completion-method').textContent = `${done} / ${denominator} named production qualification obligations evidenced; Nix ${S.evidenceRun.nixFull.passed}/${S.evidenceRun.nixFull.failed}, disposable PostgreSQL ${S.evidenceRun.disposablePostgresqlFull.passed}/${S.evidenceRun.disposablePostgresqlFull.failed}, targeted P4 ${S.evidenceRun.targetedP4.passed}/${S.evidenceRun.targetedP4.failed}; test counts excluded.`;
stages.forEach((stage, index) => {
  const article = document.createElement('article');
  article.className = 'stage-card'; article.tabIndex = 0;
  article.innerHTML = `<div class="stage-title"><span class="stage-index">${String(index + 1).padStart(2, '0')}</span><h3>${stage.label}</h3></div><div class="status-columns"><div><span class="field-label">Prototype/reference</span><span class="status-chip ${statusClass(stage.prototype)}">${stage.prototype}</span></div><div><span class="field-label">Production adoption</span><span class="status-chip ${statusClass(stage.adoption)}">${stage.adoption}</span></div><div><span class="field-label">Evidence</span><span class="status-chip ${statusClass(stage.evidence)}">${stage.evidence}</span></div></div><dl class="stage-details"><div><dt>Local/narrow evidence</dt><dd>${stage.tests}</dd></div><div><dt>Production blockers</dt><dd>${stage.blockers}</dd></div><div><dt>Snapshot</dt><dd><code>${S.snapshot}</code></dd></div></dl>`;
  grid.append(article);
});
