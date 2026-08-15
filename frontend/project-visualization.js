(() => {
  'use strict';
  const S = window.VISUALIZATION_STATUS;
  const esc = value => String(value).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const statusClass = value => value.toLowerCase();
  const components = [
    ['files','Local files','done','Prototype/reference fixtures and browser verification.','Qualify real source contract.'],
    ['connectors','Connectors','partial','Cursor comparator/version: nango-numeric-v1. No live endpoint or credentials.','Provision approved provider and validate connector.'],
    ['sync','Batch sync + workflow','partial','Batch atomicity implemented; workflow remains un-deployed.','Fresh PostgreSQL failure/recovery validation.'],
    ['staged-raw','Staged raw lifecycle','partial','Staging, orphan registry, and bounded sweeper implemented.','Live KMS/S3 and provider rehearsal.'],
    ['authority','PostgreSQL authority','partial','Latest validation 36/37; two issues fixed; fresh rerun pending. Migration 005.','Pass fresh failure/recovery matrix.'],
    ['canonical','Canonical ObjectKey purge namespace','done','Canonical namespace includes provider, tenant, connector, source instance, object ID.','Production purge and retention evidence.'],
    ['retrieval','Retrieval + query','done','Local ACL-filtered lexical search/report.','Production hosting and SLO evidence.'],
    ['answer','Answer boundary','deferred','Prototype UI contract; model/provider deferred.','Provider, citation, and groundedness qualification.'],
    ['consumers','Consumers','partial','One-page hub and static report consumer.','Deployment, access, and on-call evidence.']
  ];
  const dependencies = [
    ['Ingestion',[['Local files','done','Prototype fixtures','Real source contract'],['Connector cursor comparator/version','partial','Connector contract','Live provider validation'],['Batch atomicity','partial','Local remediation tests','Fresh PostgreSQL matrix']]],
    ['Processing',[['Staged raw lifecycle','partial','Migration 004/raw contracts','Live KMS/S3'],['Orphan registry / sweeper','partial','Bounded local implementation','Provider failure rehearsal'],['Canonical ObjectKey purge','done','Migration 005 and namespace tests','Production purge evidence']]],
    ['Storage / reliability',[['PostgreSQL authority','partial','36/37 latest validation; two issues fixed','Fresh rerun'],['Lease-owner retry metadata','done','Retry ownership and attempt metadata','Production workload evidence'],['Fresh failure/recovery matrix','partial','Latest run incomplete','Next roadmap item']]],
    ['Production readiness',[['Live providers / endpoints / credentials','blocked','None configured','Non-production provider environment'],['SEC/OPS','blocked','Explicit NO-GO','Approval evidence'],['Production deployment','blocked','No live deployment','Release and on-call evidence']]]
  ];
  const roadmap = [
    ['Prototype/reference','Local fixtures and one-page hub','DONE','Browser-rendered reference evidence; not production.'],
    ['Prototype/reference','Backend remediation set','PARTIAL','Atomicity, cursor semantics, staged raw/orphans, lease metadata, ObjectKey purge namespace implemented.'],
    ['Production-shaped non-prod','PostgreSQL authority validation','PARTIAL','36/37 latest; two issues fixed; fresh rerun pending.'],
    ['Production-shaped non-prod','Live provider environment','BLOCKED','Live providers, endpoints, and credentials absent.'],
    ['Production qualification/release','SEC/OPS and production release','BLOCKED','SEC/OPS NO-GO; deployment, RPO/RTO, SLO, and approval evidence absent.']
  ];
  const city = [
    ['frontend','HTML/CSS/JS','interface',[['frontend/project-visualization.html','Hub shell','browser rendering','PARTIAL','primary prototype/reference visualization'],['frontend/project-visualization.js','Hub renderer','browser rendering','PARTIAL','primary prototype/reference visualization'],['frontend/visualization-status.json','Shared facts','JSON parse','DONE','shared status data; not production evidence']]],
    ['kb_pipeline','Python','service',[['kb_pipeline/postgres_authority.py','PostgreSQL authority','local tests','PARTIAL','latest 36/37; fresh rerun pending'],['kb_pipeline/nango_adapter.py','Connector adapter','remediation tests','PARTIAL','cursor comparator/version; live provider absent'],['kb_pipeline/protocol.py','Canonical protocol','local tests','DONE','ObjectKey namespace and batch contract']]],
    ['migrations','SQL','service',[['migrations/004_ingestion_remediation.sql','Staged raw lifecycle','migration review','PARTIAL','orphan registry/sweeper; live storage absent'],['migrations/005_canonical_object_keys.sql','Canonical ObjectKey','migration review','DONE','purge namespace migration']]],
    ['tests','Python','test',[['tests/test_remediation_lane.py','Remediation lane','passing','PARTIAL','local validation; PostgreSQL rerun pending'],['tests/test_phase4_qa.py','Atomic acceptance','passing','PARTIAL','local full suite only']]],
    ['docs','Markdown','knowledge',[['docs/pilot-readiness.md','Pilot readiness','reviewed','BLOCKED','SEC/OPS NO-GO'],['docs/runbook.md','Runbook','reviewed','PARTIAL','production rehearsal absent']]]
  ];
  function $(selector) { return document.querySelector(selector); }
  $('#suite-count').textContent = `${S.suite.run}/${S.suite.pass}/${S.suite.skipped}`;
  $('#postgres-count').textContent = `${S.postgresValidation.latestPass}/${S.postgresValidation.latestRun}`;
  $('#next-step').textContent = S.next;
  $('#evidence-list').innerHTML = S.evidence.map(item => `<li>${esc(item)}</li>`).join('');
  const svgNS = 'http://www.w3.org/2000/svg';
  const points = (x,y) => Array.from({length:6},(_,i) => { const a=Math.PI/3*i-Math.PI/6; return `${x+66*Math.cos(a)},${y+47*Math.sin(a)}`; }).join('');
  const positions = [[70,180],[205,180],[340,180],[475,180],[610,180],[745,180],[880,180],[1015,180],[1080,300]];
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
