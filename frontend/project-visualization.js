(() => {
  'use strict';
  const S = window.VISUALIZATION_STATUS;
  const esc = value => String(value).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const statusClass = value => value.toLowerCase();
  const components = [
    ['files','Local files','done','Prototype/reference fixtures and browser verification.','Qualify real source contract.'],
    ['connectors','Connectors','partial','12/12 connector contract tests passed; real provider endpoints and credentials absent.','Obtain approved non-production provider configuration, then rerun live integration.'],
    ['sync','Batch sync + workflow','partial','Batch atomicity validated; live Temporal absent.','Use configured non-prod provider environment.'],
    ['staged-raw','Staged raw lifecycle','partial','Staged raw and orphan lifecycle validated; live KMS/S3 absent.','Use configured non-prod provider environment.'],
    ['authority','P4 PostgreSQL authority ledger','done','Semantic identity, authority sequence, outbox envelope, tombstone guards, and citation verification are implemented in reference core.','Production qualification remains open; authority remains correctness source.'],
    ['canonical','Canonical ObjectKey purge namespace','done','Canonical namespace includes provider, tenant, connector, source instance, object ID.','Production purge and retention evidence.'],
    ['retrieval','Derived projection + FTS','done','Projection worker, watermark/barrier states, and ACL-filtered PostgreSQL FTS query contract.','Production worker and FTS qualification.'],
    ['answer','Answer boundary','deferred','Prototype UI contract; model/provider deferred.','Provider, citation, and groundedness qualification.'],
    ['consumers','Consumers','partial','One-page hub and static report consumer.','Deployment, access, and on-call evidence.']
  ];
  const dependencies = [
    ['Ingestion',[['Local files','done','Prototype fixtures','Real source contract'],['Connector cursor comparator/version','done','Local validation','External connector environment'],['Batch atomicity','done','21/21 targeted matrix','External provider environment']]],
    ['Processing',[['Staged raw lifecycle','done','Local validation','Non-prod KMS/S3'],['Orphan registry / sweeper','done','Local validation','Non-prod provider failure rehearsal'],['Canonical ObjectKey purge','done','Canonical purge namespace validated','Production purge evidence']]],
    ['Storage / reliability',[['PostgreSQL authority','done','P4 identity, sequence, envelope, and lifecycle contracts','Production qualification'],['Projection worker / watermark','partial','Derived worker and barrier states observed','Production worker evidence'],['Lease-owner retry metadata','done','Outbox ownership/retry validated','Production workload evidence'],['Migrations 001-006','done','Idempotency and P4 projection schema reviewed','Production deployment evidence']]],
    ['P4 observability',[['Ingest outcomes','done','accepted / duplicate / stale / gap / conflict / rejected / failed','Production telemetry evidence'],['Barrier states','done','fresh / pending / stale / blocked / timeout','Production latency and alert evidence'],['Provenance / failure ledger','partial','Citation, failure injection, replay evidence local/mock','Production recovery rehearsal']]],
    ['Production readiness',[['Live providers / endpoints / credentials','blocked','KMS/S3/OIDC/Temporal/OTel absent','External provider environment integration'],['SEC/OPS','blocked','Explicit NO-GO','Approval evidence'],['Production deployment','blocked','No live deployment','Release and on-call evidence']]]
  ];
  const roadmap = [
    ['Prototype/reference','Local fixtures and one-page hub','DONE','Browser-rendered reference evidence; not production.'],
    ['Prototype/reference','Backend remediation set','DONE','Atomicity, cursor semantics, staged raw/orphans, outbox ownership/retry, and canonical purge namespace locally validated.'],
    ['Production-shaped non-prod','PostgreSQL authority and P4 observation validation','DONE','P4 identity, envelope, projection, barriers, lifecycle, provenance, and citation contracts; full suite 189 passed / 15 skipped.'],
    ['Production-shaped non-prod','Live connector integration','PARTIAL','Exactly one next item: obtain approved non-production provider configuration, then rerun live integration.'],
    ['Production qualification/release','SEC/OPS and production release','BLOCKED','SEC/OPS NO-GO; deployment, RPO/RTO, SLO, and approval evidence absent.']
  ];
  const city = [
    ['frontend','HTML/CSS/JS','interface',[['frontend/project-visualization.html','Hub shell','browser rendering','PARTIAL','primary prototype/reference visualization'],['frontend/project-visualization.js','Hub renderer','browser rendering','PARTIAL','P4 observational surfaces; no mutation controls'],['frontend/p4-observations.css','P4 observation styles','syntax check','DONE','responsive/read-only status presentation'],['frontend/visualization-status.json','Shared facts','JSON parse','DONE','P4 facts; not production evidence']]],
    ['kb_pipeline','Python','service',[['kb_pipeline/phase4_core.py','P4 authority/projection core','P4 targeted suite','DONE','local/mock evidence; production qualification absent'],['kb_pipeline/postgres_authority.py','PostgreSQL authority','21/21 matrix; 5/5 custom checks','DONE','local evidence; production qualification absent'],['kb_pipeline/nango_adapter.py','Connector adapter','remediation checks','DONE','cursor comparator/version validated; external connector absent'],['kb_pipeline/protocol.py','Canonical protocol','local tests','DONE','canonical purge namespace and batch contract']]],
    ['migrations','SQL','service',[['migrations/004_ingestion_remediation.sql','Staged raw lifecycle','migration review','PARTIAL','orphan registry/sweeper; live storage absent'],['migrations/005_canonical_object_keys.sql','Canonical ObjectKey','migration review','DONE','purge namespace migration'],['migrations/006_phase4_projection.sql','Projection/watermark schema','migration review','PARTIAL','derived projection; production deployment absent']]],
    ['tests','Python','test',[['tests/test_remediation_lane.py','Remediation lane','5/5 passing','DONE','custom local validation'],['tests/test_phase4_qa.py','Atomic acceptance','21/21 passing','DONE','targeted local matrix']]],
    ['docs','Markdown','knowledge',[['docs/pilot-readiness.md','Pilot readiness','reviewed','BLOCKED','SEC/OPS NO-GO'],['docs/runbook.md','Runbook','reviewed','PARTIAL','production rehearsal absent']]]
  ];
  components[1][3] = `Nix full ${S.evidenceRun.nixFull.passed}/${S.evidenceRun.nixFull.failed}; real provider endpoints and credentials absent.`;
  dependencies[0][1][2][2] = `Nix full ${S.evidenceRun.nixFull.passed}/${S.evidenceRun.nixFull.failed}`;
  dependencies[2][1][0][2] = `Disposable PostgreSQL ${S.evidenceRun.disposablePostgresqlFull.passed}/${S.evidenceRun.disposablePostgresqlFull.failed}; targeted P4 ${S.evidenceRun.targetedP4.passed}/${S.evidenceRun.targetedP4.failed}`;
  city[1][3][1][3] = `Nix full ${S.evidenceRun.nixFull.passed}/${S.evidenceRun.nixFull.failed}`;
  city[2][3][0][3] = `Labeled scenarios ${S.evidenceRun.labels.passed}/${S.evidenceRun.labels.total}`;
  function $(selector) { return document.querySelector(selector); }
  const runLabel = run => `${run.passed}/${run.failed}`;
  document.querySelector('#summary > div:first-child p:last-child').textContent = `Remediation ${S.commits.remediation}; ${S.remediationStage}; ${S.evidenceScope}. Prior test run ${S.evidenceRun.runDate}. Docs metadata ${S.commits.docs}. ${S.evidenceLabel}`;
  const metricGrid = document.querySelector('.metric-grid');
  metricGrid.replaceChildren(...[
    ['Nix full', runLabel(S.evidenceRun.nixFull), 'passed / failed'],
    ['Disposable PostgreSQL', runLabel(S.evidenceRun.disposablePostgresqlFull), 'passed / failed'],
    ['Targeted P4', runLabel(S.evidenceRun.targetedP4), 'passed / failed'],
    ['Labeled scenarios', `${S.evidenceRun.labels.passed}/${S.evidenceRun.labels.total}`, 'passed / total']
  ].map(([label, value, suffix]) => { const item = document.createElement('div'); item.innerHTML = `<strong>${value}</strong><span>${label} ${suffix}</span>`; return item; }));
  $('#next-step').textContent = S.next;
  $('#evidence-list').innerHTML = S.evidence.map(item => `<li>${esc(item)}</li>`).join('');
  $('#scenario-list').innerHTML = S.scenarios.map(item => `<li>${esc(item)} <span class="status-chip done">PASS</span></li>`).join('');
  const p4 = S.p4;
  const p4Cards = [
    ['Semantic identity', `(${p4.identity.tenant}, ${p4.identity.source}, ${p4.identity.source_id})`, `Authority: ${p4.identity.authority}`],
    ['Authority sequence', `accepted ${p4.authoritySequence.accepted} · applied ${p4.authoritySequence.applied} · ${p4.authoritySequence.state.toUpperCase()}`, p4.authoritySequence.source],
    ['Outbox envelope', `${p4.outbox.protocol_version} · ${p4.outbox.operation} · revision ${p4.outbox.revision}`, `event ${p4.outbox.event_id}; idempotency ${p4.outbox.idempotency_key}`],
    ['Projection worker / watermark', `${p4.projection.worker} · ${p4.projection.projection}`, `watermark ${p4.projection.watermark} · ${p4.projection.state.toUpperCase()} · ${p4.projection.source}`],
    ['FTS status', p4.fts.state.toUpperCase(), `${p4.fts.index}; ${p4.fts.source}`],
    ['Barrier states', p4.barriers.join(' · '), 'fresh / pending / stale / blocked / timeout are explicit state text']
  ];
  $('#p4-cards').innerHTML = p4Cards.map(([title, value, note]) => `<article class="p4-card"><h3>${esc(title)}</h3><strong>${esc(value)}</strong><p>${esc(note)}</p></article>`).join('');
  const ledger = [
    ['Ingest outcomes', p4.ingestOutcomes.join(', '), 'Authority ingest classification; observational fixture'],
    ['Delete / tombstone / purge / replay', p4.lifecycle.join(' · '), 'Authority lifecycle and replay contracts; projection reflects tombstone'],
    ['Provenance / citation evidence', `${p4.provenance.raw_reference}; ${p4.provenance.content_hash}`, `${p4.provenance.citation}; ${p4.provenance.verification}`],
    ['Failure injection', 'OBSERVED', p4.failureEvidence.injection],
    ['Evidence ledger', 'RECORDED', p4.failureEvidence.ledger],
    ['Recovery boundary', 'MOCK / REFERENCE', p4.failureEvidence.recovery],
    ['Qualification flag', 'production_qualification=false', 'Visual and correctness claims remain non-production']
  ];
  $('#p4-ledger').innerHTML = ledger.map(row => `<tr><th scope="row">${esc(row[0])}</th><td><strong>${esc(row[1])}</strong></td><td>${esc(row[2])}</td></tr>`).join('');
  $('#p4-list').innerHTML = ledger.map(row => `<li><strong>${esc(row[0])}:</strong> ${esc(row[1])}. ${esc(row[2])}</li>`).join('');
  $('#p4-status').textContent = 'Ready. Static MOCK / REFERENCE snapshot; no live provider or mutation state connected.';
  const svgNS = 'http://www.w3.org/2000/svg';
  const points = (x,y) => Array.from({length:6},(_,i) => { const a=Math.PI/3*i-Math.PI/6; return `${x+66*Math.cos(a)},${y+47*Math.sin(a)}`; }).join(' ');
  const positions = [[75,180],[195,180],[315,180],[435,180],[555,180],[675,180],[795,180],[915,180],[1025,180]];
  const arrows=$('#flow-arrows'), nodes=$('#flow-nodes');
  positions.slice(0,components.length-1).forEach((p,i) => { const l=document.createElementNS(svgNS,'line'); l.setAttribute('x1',p[0]+68); l.setAttribute('y1',p[1]); l.setAttribute('x2',positions[i+1][0]-68); l.setAttribute('y2',positions[i+1][1]); l.setAttribute('class','flow-arrow'); arrows.append(l); });
  const detail = (item,target) => { target.innerHTML=`<h3>${esc(item[1])}</h3><dl><div><dt>Status</dt><dd>${esc(item[2].toUpperCase())}</dd></div><div><dt>What exists</dt><dd>${esc(item[3])}</dd></div><div><dt>Remaining work</dt><dd>${esc(item[4])}</dd></div><div><dt>Evidence boundary</dt><dd>Prototype/reference or local validation; not live production.</dd></div></dl>`; };
  components.forEach((item,i) => { const [x,y]=positions[i], g=document.createElementNS(svgNS,'g'); g.setAttribute('class',`flow-node ${statusClass(item[2])}`); g.setAttribute('tabindex','0'); g.setAttribute('role','button'); g.setAttribute('aria-label',`${item[1]}, ${item[2]}`); const p=document.createElementNS(svgNS,'polygon'); p.setAttribute('points',points(x,y)); g.append(p); const t=document.createElementNS(svgNS,'text'); t.setAttribute('x',x); t.setAttribute('y',y-2); t.textContent=item[1]; g.append(t); const s=document.createElementNS(svgNS,'text'); s.setAttribute('x',x); s.setAttribute('y',y+17); s.setAttribute('class','small'); s.textContent=item[2].toUpperCase(); g.append(s); const activate=()=>detail(item,$('#flow-detail')); g.addEventListener('click',activate); g.addEventListener('keydown',e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();activate();}}); nodes.append(g); });
  $('#component-table').innerHTML=components.map(item=>`<tr><th scope="row">${esc(item[1])}</th><td><span class="${statusClass(item[2])}">${esc(item[2].toUpperCase())}</span></td><td>${esc(item[3])}</td><td>${esc(item[4])}</td></tr>`).join('');
  dependencies.forEach(([groupName,items])=>{ const section=document.createElement('section'); section.className='dependency-group'; section.innerHTML=`<h3>${esc(groupName)}</h3><div class="hex-grid"></div>`; const grid=section.querySelector('.hex-grid'); items.forEach(item=>{ const button=document.createElement('button'); button.className=`hex ${item[1]}`; button.type='button'; button.innerHTML=`${esc(item[0])}<small>${esc(item[1].toUpperCase())}</small>`; button.addEventListener('click',()=>{$('#dependency-detail').innerHTML=`<h3>${esc(item[0])}</h3><dl><div><dt>Status</dt><dd>${esc(item[1].toUpperCase())}</dd></div><div><dt>Depends on</dt><dd>${esc(item[2])}</dd></div><div><dt>Unlocks</dt><dd>${esc(item[3])}</dd></div><div><dt>Next action</dt><dd>${esc(S.next)}</dd></div></dl>`;}); grid.append(button); $('#dependency-list').insertAdjacentHTML('beforeend',`<li><strong>${esc(groupName)} — ${esc(item[0])}:</strong> ${esc(item[1].toUpperCase())}; depends on ${esc(item[2])}; unlocks ${esc(item[3])}.</li>`); }); $('#dependency-groups').append(section); });
  S.horizons.forEach(horizon=>{ const items=roadmap.filter(row=>row[0]===horizon), lane=document.createElement('section'); lane.className='road-lane'; lane.innerHTML=`<h3>${esc(horizon)}</h3><div class="road-items">${items.map(row=>`<div class="road-item"><strong>${esc(row[1])}</strong><span class="${statusClass(row[2])}">${esc(row[2])}</span><small>${esc(row[3])}</small></div>`).join('')}</div>`; $('#roadmap-lanes').append(lane); });
  $('#roadmap-table').innerHTML=roadmap.map(row=>`<tr><td>${esc(row[0])}</td><th scope="row">${esc(row[1])}</th><td><span class="${statusClass(row[2])}">${esc(row[2])}</span></td><td>${esc(row[3])}</td></tr>`).join('');
  const cityColors={interface:'#168aad',service:'#6d4c9f',test:'#a85e16',knowledge:'#287052'};
  city.forEach(([districtName,language,style,buildings])=>{ const district=document.createElement('section'); district.className='district'; district.style.setProperty('--district-color',cityColors[style]); district.innerHTML=`<h3>${esc(districtName)}</h3><p>${esc(language)} · ${buildings.length} buildings</p><div class="buildings"></div>`; const root=district.querySelector('.buildings'); buildings.forEach(([path,loc,tests,state,production])=>{ const b=document.createElement('button'); b.className='building'; b.style.height=`${Math.max(44,Math.sqrt(200/620)*145)}px`; b.style.background=cityColors[style]; b.textContent=path.split('/').pop(); b.setAttribute('aria-label',`${path}, ${loc}, ${state}`); b.addEventListener('click',()=>{$('#city-detail').innerHTML=`<h3>${esc(path.split('/').pop())}</h3><p>${esc(path)}</p><dl><div><dt>Scope</dt><dd>${esc(loc)}</dd></div><div><dt>Tests / checks</dt><dd>${esc(tests)}</dd></div><div><dt>Status</dt><dd>${esc(state)}</dd></div><div><dt>Production relevance</dt><dd>${esc(production)}</dd></div></dl>`;}); root.append(b); $('#city-table').insertAdjacentHTML('beforeend',`<tr><th scope="row">${esc(path)}</th><td>${esc(loc)}</td><td>${esc(tests)}</td><td><span class="${statusClass(state)}">${esc(state)}</span></td><td>${esc(production)}</td></tr>`); }); $('#city-map').append(district); });
  $('#city-status').textContent='Map ready. Static evidence snapshot; live metrics and provider data unavailable.';
})();
