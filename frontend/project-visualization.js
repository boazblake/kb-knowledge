(() => {
  'use strict';
  const S = window.VISUALIZATION_STATUS;
  const statusClass = value => value.toLowerCase();
  const components = [
    ['files','Local files','done','UTF-8 scan; narrow local fixtures.','Qualify real source contract.'],
    ['connectors','Connectors','partial','Nango experiment; no provider evidence.','Production identity/KMS/provider evidence.'],
    ['sync','Sync + workflow','partial','Temporal boundary; no deployed workflow evidence.','Deploy workflow; rehearse failure.'],
    ['storage','Raw storage + KMS/S3','partial','Encrypted raw reference; contracts only.','Live KMS/S3 and decrypt read path.'],
    ['canonical','Canonical model','done','Changes, idempotency, quarantine.','Approved real-data semantics.'],
    ['retrieval','Retrieval + query','done','ACL-filtered lexical search/report.','Production hosting and SLO evidence.'],
    ['answer','Answer boundary','deferred','UI contract; model/provider deferred.','Citation, model, groundedness evidence.'],
    ['consumers','Consumers','partial','Static UI and report consumer.','Deployment/access/on-call evidence.']
  ];
  const dependencies = [
    ['Ingestion',[['Local files','done','Local plaintext source','Canonicalization / ACL'],['External connectors','blocked','Stable connector contract','Broader source ingestion']]],
    ['Processing',[['Canonicalize / ACL','done','Local files','SQLite state'],['Nango adapter','partial','Connector contract','Experimental source sync'],['LLM synthesis','deferred','Citation-ready contract','Grounded answer synthesis']]],
    ['Storage / reliability',[['SQLite','done','Canonicalization / ACL','Ledger / outbox'],['Ledger / outbox','done','SQLite','Projections / FTS'],['Recovery rehearsal','done','SQLite and ledger','Local recovery evidence'],['Production DR','blocked','Production RPO / RTO','Qualified disaster recovery']]],
    ['Search / report',[['Projections / FTS','done','Ledger / outbox','Search and report'],['Search + report','done','Projections / FTS','Authenticated UI reporting']]],
    ['Production readiness',[['Identity / KMS','blocked','Production identity and KMS','Production access boundary'],['Alerts / on-call','blocked','Operational monitoring','Supported service response'],['Real-data pilot','blocked','All production gates','Real-data pilot']]]
  ];
  const roadmap = [
    ['Prototype/reference','Local files + browser UI','DONE','Local/narrow fixtures and frontend browser verification.'],
    ['Prototype/reference','Canonical changes + ACL lexical retrieval','DONE','Protocol, fixture, local API/search evidence.'],
    ['Production-shaped non-prod','Disposable provider environment','BLOCKED','No endpoint or credentials; zero live calls.'],
    ['Production-shaped non-prod','Temporal, KMS/S3, PostgreSQL authority','PARTIAL','Contract tests and PostgreSQL Nix narrow evidence; live services absent.'],
    ['Production-shaped non-prod','Purge/recovery + load/SLO harness','PARTIAL','Synthetic-local tests; provider rehearsal and production evidence absent.'],
    ['Production qualification/release','Answer/provider boundary','DEFERRED','Provider, groundedness, and citation qualification absent.'],
    ['Production qualification/release','Deployment, on-call, SEC/OPS gates','BLOCKED','Deployment, RPO/RTO, SLO, and approval evidence absent.']
  ];
  const city = [
    ['frontend','HTML/CSS/JS','interface',[['frontend/index.html',196,'browser verification','DONE','reference UI only'],['frontend/app.js',653,'browser smoke','PARTIAL','reference UI only'],['frontend/styles.css',127,'unavailable','PARTIAL','reference UI only']]],
    ['kb_pipeline','Python','service',[['kb_pipeline/storage.py',620,'unit + integration','PARTIAL','local/reference'],['kb_pipeline/postgres_authority.py',240,'PostgreSQL Nix narrow','PARTIAL','narrow slice only'],['kb_pipeline/security.py',310,'OIDC local JWKS packet','PARTIAL','live provider absent'],['kb_pipeline/api.py',190,'smoke','PARTIAL','deployment not qualified']]],
    ['tests','Python','test',[['tests/test_gate6.py',180,'purge/recovery + synthetic load/SLO','PARTIAL','synthetic-local'],['tests/test_production_oidc.py',120,'local JWKS','PARTIAL','live provider absent']]],
    ['docs','Markdown','knowledge',[['docs/pilot-readiness.md',180,'reviewed','BLOCKED','NO-GO'],['docs/phase2-sre-review.md',130,'reviewed','BLOCKED','RPO/RTO and production SLO absent']]]
  ];
  const $ = selector => document.querySelector(selector);
  const esc = value => String(value).replace(/[&<>"']/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
  $('#provider-count').textContent = `${S.provider.boundary.run}/${S.provider.boundary.pass}/${S.provider.boundary.skipped}`;
  $('#suite-count').textContent = `${S.suite.run}/${S.suite.pass}/${S.suite.skipped}`;
  $('#next-step').textContent = S.next;
  $('#evidence-list').innerHTML = S.evidence.map(item => `<li>${esc(item)}</li>`).join('');

  const svgNS = 'http://www.w3.org/2000/svg';
  const points = (x, y) => Array.from({length: 6}, (_, i) => { const a = Math.PI / 3 * i - Math.PI / 6; return `${x + 66 * Math.cos(a)},${y + 47 * Math.sin(a)}`; }).join(' ');
  const positions = [[70,180],[205,180],[340,180],[475,180],[610,180],[745,180],[880,180],[1015,180]];
  const flowItems = components;
  const arrows = $('#flow-arrows'); const nodes = $('#flow-nodes');
  positions.slice(0, flowItems.length - 1).forEach((pos, index) => { const line = document.createElementNS(svgNS, 'line'); line.setAttribute('x1', pos[0] + 68); line.setAttribute('y1', pos[1]); line.setAttribute('x2', positions[index + 1][0] - 68); line.setAttribute('y2', positions[index + 1][1]); line.setAttribute('class', 'flow-arrow'); arrows.append(line); });
  const detail = (item, target) => { target.innerHTML = `<h3>${esc(item[1])}</h3><dl><div><dt>Status</dt><dd>${esc(item[2].toUpperCase())}</dd></div><div><dt>What exists</dt><dd>${esc(item[3])}</dd></div><div><dt>Remaining work</dt><dd>${esc(item[4])}</dd></div><div><dt>Production gate</dt><dd>${item[2] === 'done' ? 'Local/reference only; production qualification still required.' : 'Blocks production qualification.'}</dd></div></dl>`; };
  flowItems.forEach((item, index) => { const [x, y] = positions[index]; const group = document.createElementNS(svgNS, 'g'); group.setAttribute('class', `flow-node ${statusClass(item[2])}`); group.setAttribute('tabindex', '0'); group.setAttribute('role', 'button'); group.setAttribute('aria-label', `${item[1]}, ${item[2]}`); const poly = document.createElementNS(svgNS, 'polygon'); poly.setAttribute('points', points(x, y)); group.append(poly); const text = document.createElementNS(svgNS, 'text'); text.setAttribute('x', x); text.setAttribute('y', y - 2); text.textContent = item[1]; group.append(text); const small = document.createElementNS(svgNS, 'text'); small.setAttribute('x', x); small.setAttribute('y', y + 17); small.setAttribute('class', 'small'); small.textContent = item[2].toUpperCase(); group.append(small); const activate = () => detail(item, $('#flow-detail')); group.addEventListener('click', activate); group.addEventListener('keydown', event => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); activate(); } }); nodes.append(group); });
  $('#component-table').innerHTML = flowItems.map(item => `<tr><th scope="row">${esc(item[1])}</th><td><span class="${statusClass(item[2])}">${esc(item[2].toUpperCase())}</span></td><td>${esc(item[3])}</td><td>${esc(item[4])}</td></tr>`).join('');

  const dependencyDetail = $('#dependency-detail'); const dependencyList = $('#dependency-list');
  dependencies.forEach(([groupName, items]) => { const section = document.createElement('section'); section.className = 'dependency-group'; section.innerHTML = `<h3>${esc(groupName)}</h3><div class="hex-grid"></div>`; const grid = section.querySelector('.hex-grid'); items.forEach(item => { const button = document.createElement('button'); button.className = `hex ${item[1]}`; button.type = 'button'; button.innerHTML = `${esc(item[0])}<small>${esc(item[1].toUpperCase())}</small>`; const activate = () => { dependencyDetail.innerHTML = `<h3>${esc(item[0])}</h3><dl><div><dt>Status</dt><dd>${esc(item[1].toUpperCase())}</dd></div><div><dt>Depends on</dt><dd>${esc(item[2])}</dd></div><div><dt>Unlocks</dt><dd>${esc(item[3])}</dd></div><div><dt>Next action</dt><dd>${esc(S.next)}</dd></div></dl>`; }; button.addEventListener('click', activate); grid.append(button); dependencyList.insertAdjacentHTML('beforeend', `<li><strong>${esc(groupName)} — ${esc(item[0])}:</strong> ${esc(item[1].toUpperCase())}; depends on ${esc(item[2])}; unlocks ${esc(item[3])}.</li>`); }); $('#dependency-groups').append(section); });

  const roadmapRoot = $('#roadmap-lanes'); S.horizons.forEach(horizon => { const lane = document.createElement('section'); lane.className = 'road-lane'; lane.innerHTML = `<h3>${esc(horizon)}</h3><div class="road-items"></div>`; const items = roadmap.filter(row => row[0] === horizon); lane.querySelector('.road-items').innerHTML = items.map(row => `<div class="road-item"><strong>${esc(row[1])}</strong><span class="${statusClass(row[2])}">${esc(row[2])}</span><small>${esc(row[3])}</small></div>`).join(''); roadmapRoot.append(lane); });
  $('#roadmap-table').innerHTML = roadmap.map(row => `<tr><td>${esc(row[0])}</td><th scope="row">${esc(row[1])}</th><td><span class="${statusClass(row[2])}">${esc(row[2])}</span></td><td>${esc(row[3])}</td></tr>`).join('');

  const cityColors = {interface:'#168aad', service:'#6d4c9f', test:'#a85e16', knowledge:'#287052'}; const cityMap = $('#city-map');
  city.forEach(([districtName, language, style, buildings]) => { const district = document.createElement('section'); district.className = 'district'; district.style.setProperty('--district-color', cityColors[style]); district.innerHTML = `<h3>${esc(districtName)}</h3><p>${esc(language)} · ${buildings.length} buildings</p><div class="buildings"></div>`; const buildingRoot = district.querySelector('.buildings'); buildings.forEach(([path, loc, tests, state, production]) => { const button = document.createElement('button'); button.className = 'building'; button.style.height = `${Math.max(44, Math.sqrt(loc / 620) * 145)}px`; button.style.background = cityColors[style]; button.textContent = path.split('/').pop(); button.setAttribute('aria-label', `${path}, ${loc} lines, ${state}`); button.addEventListener('click', () => { $('#city-detail').innerHTML = `<h3>${esc(path.split('/').pop())}</h3><p>${esc(path)}</p><dl><div><dt>Physical LOC</dt><dd>${loc.toLocaleString()}</dd></div><div><dt>Tests / checks</dt><dd>${esc(tests)}</dd></div><div><dt>Status</dt><dd>${esc(state)}</dd></div><div><dt>Production relevance</dt><dd>${esc(production)}</dd></div></dl>`; }); buildingRoot.append(button); $('#city-table').insertAdjacentHTML('beforeend', `<tr><th scope="row">${esc(path)}</th><td>${loc.toLocaleString()}</td><td>${esc(tests)}</td><td><span class="${statusClass(state)}">${esc(state)}</span></td><td>${esc(production)}</td></tr>`); }); cityMap.append(district); });
  $('#city-status').textContent = 'Map ready. Static snapshot loaded; missing metrics remain unavailable.';
})();
