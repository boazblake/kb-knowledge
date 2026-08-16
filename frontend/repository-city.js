const map = document.querySelector('#city-map');
const table = document.querySelector('#city-table');
const detail = document.querySelector('#city-detail');
const status = document.querySelector('#city-status');
const S = window.VISUALIZATION_STATUS || (() => { const request = new XMLHttpRequest(); request.open('GET', 'visualization-status.json', false); request.send(); const data = JSON.parse(request.responseText); if (!data.commits || data.production_qualification !== false) throw new Error('visualization status mismatch'); return data; })();
const banner=document.createElement('aside');banner.className='shared-status';banner.setAttribute('aria-label','Authoritative SRE snapshot');banner.innerHTML=`<strong>${S.decision}</strong><span>HEAD <code>${S.commits.head}</code> · tested ancestor <code>${S.commits.tested}</code> · migrations ${S.migrations.freshRun} (second run ${S.migrations.secondRun})</span><span>BDD ${S.statuses.bdd} · SRE ${S.statuses.sre} · test-operator ${S.statuses.qa} · production ${S.statuses.production}</span><span>${S.dirtyWorktree}</span>`;document.querySelector('main')?.prepend(banner);
const freshness = document.querySelector('#city-freshness');
const colors = {interface:'#168aad', service:'#6d4c9f', test:'#d27b2d', knowledge:'#3c8d68'};
const safe = (value, fallback = 'Unavailable') => typeof value === 'string' && value.trim() ? value : fallback;
const canonicalStatus = value => ({prototype:'DONE', complete:'DONE', unproven:'PARTIAL', partial:'PARTIAL', blocked:'BLOCKED', deferred:'DEFERRED'})[String(value).toLowerCase()] || 'DEFERRED';
function showBuilding(building, district) {
  detail.innerHTML = `<h3>${building.path.split('/').pop()}</h3><p class="detail-path">${building.path}</p><dl class="stage-details"><div><dt>Physical LOC</dt><dd>${Number.isFinite(building.loc) ? building.loc.toLocaleString() : 'Unavailable'}</dd></div><div><dt>File size</dt><dd>${Number.isFinite(building.bytes) ? `${Math.round(building.bytes / 1024)} KB` : 'Unavailable'}</dd></div><div><dt>Language / style</dt><dd>${district.language} · ${district.style}</dd></div><div><dt>Dependencies / flow</dt><dd>Snapshot does not include import edges.</dd></div><div><dt>Tests / checks</dt><dd>${safe(building.tests)}</dd></div><div><dt>Status</dt><dd>${canonicalStatus(building.status)}</dd></div><div><dt>Production relevance</dt><dd>${safe(building.production)}</dd></div></dl>`;
}
function render(payload) {
  if (!Array.isArray(payload?.districts) || !payload.districts.length) throw new Error('empty snapshot');
  const districts = payload.districts; const maxLoc = Math.max(...districts.flatMap(d => d.buildings.map(b => b.loc || 1)), 1);
  map.replaceChildren(); table.replaceChildren();
  districts.forEach((district, districtIndex) => {
    const zone = document.createElement('section'); zone.className = 'district'; zone.style.setProperty('--district-color', colors[district.style] || '#536878');
    zone.innerHTML = `<h3>${district.path}</h3><p>${district.language} · ${district.buildings.length} buildings</p>`;
    const block = document.createElement('div'); block.className = 'buildings';
    district.buildings.forEach((building, buildingIndex) => {
      const currentStatus = canonicalStatus(building.status); const b = document.createElement('button'); b.type = 'button'; b.className = `building status-${currentStatus.toLowerCase()}`; b.style.height = `${Math.max(34, Math.sqrt((building.loc || 1) / maxLoc) * 130)}px`; b.style.background = colors[district.style] || '#536878'; b.setAttribute('aria-label', `${building.path}, ${building.loc || 'unknown'} lines, ${currentStatus}`); b.title = building.path;
      b.addEventListener('click', () => showBuilding(building, district)); block.append(b);
      const row = document.createElement('tr'); row.innerHTML = `<th scope="row">${building.path}</th><td>${Number.isFinite(building.loc) ? building.loc.toLocaleString() : 'Unavailable'}</td><td>${district.language}</td><td>${safe(building.tests)}</td><td><span class="status-chip ${currentStatus.toLowerCase()}">${currentStatus}</span></td><td>${safe(building.production)}</td>`; table.append(row);
    }); zone.append(block); map.append(zone);
  });
  const stamp = safe(payload.generatedAt); freshness.textContent = `Snapshot generated ${stamp}. ${safe(payload.freshness)}. ${safe(payload.note)}`; status.textContent = `Map ready. ${S.decision} · HEAD ${S.commits.head}; tested ancestor ${S.commits.tested}. ${S.dirtyWorktree}`; status.className = 'inline-status warning';
}
const embeddedSnapshot = {
  generatedAt: 'checked-in static snapshot', freshness: 'stale-by-design',
  note: 'Illustrative metrics; missing values remain unavailable.',
  districts: [
    {path:'frontend', language:'HTML/CSS/JS', style:'interface', buildings:[
      {path:'frontend/index.html',loc:196,bytes:12100,tests:'unavailable',status:'prototype',production:'reference UI'},
      {path:'frontend/app.js',loc:653,bytes:26000,tests:'smoke',status:'partial',production:'reference UI'},
      {path:'frontend/styles.css',loc:127,bytes:21000,tests:'unavailable',status:'partial',production:'reference UI'}]},
    {path:'kb_pipeline', language:'Python', style:'service', buildings:[
      {path:'kb_pipeline/storage.py',loc:620,bytes:26000,tests:'unit + integration',status:'partial',production:'local/reference'},
      {path:'kb_pipeline/postgres_authority.py',loc:240,bytes:9800,tests:'targeted',status:'partial',production:'narrow slice only'},
      {path:'kb_pipeline/security.py',loc:310,bytes:12500,tests:'fake adapter',status:'unproven',production:'not qualified'},
      {path:'kb_pipeline/api.py',loc:190,bytes:7800,tests:'smoke',status:'prototype',production:'not qualified'}]},
    {path:'tests', language:'Python', style:'test', buildings:[
      {path:'tests/test_gate6.py',loc:180,bytes:7200,tests:'passing',status:'partial',production:'synthetic-local'},
      {path:'tests/test_production_oidc.py',loc:120,bytes:4900,tests:'passing',status:'unproven',production:'live JWKS absent'}]},
    {path:'docs', language:'Markdown', style:'knowledge', buildings:[
      {path:'docs/pilot-readiness.md',loc:180,bytes:7400,tests:'reviewed',status:'blocked',production:'NO-GO'},
      {path:'docs/phase2-sre-review.md',loc:130,bytes:5600,tests:'reviewed',status:'unproven',production:'SLO/RPO/RTO absent'}]}
  ]
};

fetch('repository-metrics.json', {headers:{Accept:'application/json'}})
  .then(response => { if (!response.ok) throw new Error('snapshot unavailable'); return response.json(); })
  .catch(() => embeddedSnapshot)
  .then(render)
  .catch(() => { status.textContent = 'Metrics snapshot unavailable. No buildings rendered; directory data is not inferred.'; status.className = 'inline-status error'; freshness.textContent = 'Repository metrics could not be loaded.'; });
