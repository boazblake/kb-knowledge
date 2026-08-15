const S = window.VISUALIZATION_STATUS || (() => { const request = new XMLHttpRequest(); request.open('GET', 'visualization-status.json', false); request.send(); const data = JSON.parse(request.responseText); if (!data.commits || data.production_qualification !== false) throw new Error('visualization status mismatch'); return data; })();
const E = S.evidenceRun;
document.querySelector('.no-go').textContent = `${S.decision} · ${S.evidenceLabel}: core ${S.commits.implementation}; ${S.evidenceScope}. Prior recorded test run ${E.runDate}.`;
document.querySelector('.evidence-note').innerHTML = `<h2>Current facts</h2><ul><li>Core ${S.commits.implementation}; ${S.evidenceScope}.</li><li>Prior recorded test run (${E.runDate}): Nix full ${E.nixFull.passed}/${E.nixFull.failed}; disposable PostgreSQL ${E.disposablePostgresqlFull.passed}/${E.disposablePostgresqlFull.failed}; targeted P4 ${E.targetedP4.passed}/${E.targetedP4.failed}; labels ${E.labels.passed}/${E.labels.total}.</li><li>Yellow live provider gap: approved non-production configuration, endpoints, and credentials absent.</li><li>Red production qualification: live provider, deployment, recovery, load/SLO, RPO/RTO, and approval evidence absent.</li><li><strong>Exactly one next roadmap item:</strong> ${S.next}</li></ul>`;
const items = [
  ['Sources / connectors','Local files','Prototype/reference','DONE','Local fixtures; frontend browser verification.'],
  ['Sources / connectors','Live connector integration','Production-shaped non-prod','PARTIAL','Exactly one next item: obtain approved non-production provider configuration, then rerun live integration.'],
  ['Sync / workflow','Temporal ingestion','Production-shaped non-prod','PARTIAL','Contract tests; live Temporal absent.'],
  ['Storage / security','PostgreSQL authority','Production-shaped non-prod','DONE',`Disposable PostgreSQL ${E.disposablePostgresqlFull.passed}/${E.disposablePostgresqlFull.failed}; targeted P4 ${E.targetedP4.passed}/${E.targetedP4.failed}.`],
  ['Storage / security','KMS + S3 raw artifacts','Production-shaped non-prod','PARTIAL','Contract tests; live KMS/S3 absent.'],
  ['Canonical model','Canonical changes + projections','Prototype/reference','DONE','Protocol and fixture evidence.'],
  ['Retrieval / answer','ACL lexical retrieval','Prototype/reference','DONE','Local API/search browser verification.'],
  ['Retrieval / answer','Answer/provider boundary','Production qualification/release','DEFERRED','Provider and groundedness qualification absent.'],
  ['Operations / recovery','Purge + recovery','Production-shaped non-prod','PARTIAL','Tests; provider rehearsal and RPO/RTO absent.'],
  ['Operations / recovery','Load + SLO harness','Production-shaped non-prod','PARTIAL','Synthetic harness; production evidence absent.'],
  ['Identity / observability','OIDC / local JWKS','Production-shaped non-prod','PARTIAL','Local packet; live provider absent.'],
  ['Identity / observability','OTel / on-call','Production qualification/release','BLOCKED','Contract tests; deployment, alerts, and approval absent.']
];
const lanes = S.horizons;
const root = document.querySelector('#roadmap-lanes');
lanes.forEach(lane => {
  const group = items.filter(item => item[2] === lane);
  const section = document.createElement('section'); section.className = 'road-lane';
  section.innerHTML = `<h3>${lane}</h3><p class="lane-count">${group.length} components · ${group.filter(x => x[3] === 'DONE').length} DONE · ${group.filter(x => x[3] === 'PARTIAL').length} PARTIAL · ${group.filter(x => x[3] === 'BLOCKED').length} BLOCKED · ${group.filter(x => x[3] === 'DEFERRED').length} DEFERRED</p><div class="road-nodes">${group.map(item => `<div class="road-node ${item[3].toLowerCase()}"><span class="road-hex" aria-hidden="true">⬡</span><strong>${item[1]}</strong><span>${item[3]}</span></div>`).join('')}</div>`;
  root.append(section);
});
items.forEach(item => {
  const row = document.createElement('tr');
  row.innerHTML = `<td>${item[0]}</td><th scope="row">${item[1]}</th><td>${item[2]}</td><td><span class="status-chip ${item[3].toLowerCase()}">${item[3]}</span></td><td>${item[4]}</td>`;
  document.querySelector('#roadmap-rows').append(row);
});
