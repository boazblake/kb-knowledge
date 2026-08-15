const S = window.VISUALIZATION_STATUS || {horizons:['Prototype/reference','Production-shaped non-prod','Production qualification/release'], next:'Qualify one approved connector against mock path, then obtain real non-production provider configuration.'};
document.querySelector('.no-go').textContent = 'Production NO-GO · MOCK / REFERENCE only: Mock E2E 14/14; fresh disposable PostgreSQL 16.9; migrations 001-005 idempotent; zero live calls.';
document.querySelector('.evidence-note').innerHTML = `<h2>Current facts</h2><ul><li>Commit e82b1d2; mock/local provider environment.</li><li>MOCK E2E: 14/14 passed across OIDC/JWKS, synthetic connector, KMS, S3, PostgreSQL authority/outbox/checkpoint, Temporal boundary, telemetry sink, tenant and failure paths.</li><li>Fresh disposable PostgreSQL 16.9; migrations 001-005 idempotent.</li><li>Missing live endpoints: KMS, S3, OIDC, Temporal, OTel; external connector absent.</li><li>Production red: load/SLO, RPO/RTO, recovery, SEC, OPS.</li><li><strong>Exactly one next roadmap item:</strong> ${S.next}</li></ul>`;
const items = [
  ['Sources / connectors','Local files','Prototype/reference','DONE','Local fixtures; frontend browser verification.'],
  ['Sources / connectors','Approved connector against mock path','Production-shaped non-prod','PARTIAL','Exactly one next item: qualify one approved connector against mock path, then obtain real non-production provider configuration.'],
  ['Sync / workflow','Temporal ingestion','Production-shaped non-prod','PARTIAL','Contract tests; live Temporal absent.'],
  ['Storage / security','PostgreSQL authority','Production-shaped non-prod','DONE','21/21 targeted matrix; 5/5 custom checks; migrations 001-005 idempotent.'],
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
