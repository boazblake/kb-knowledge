const map = document.querySelector('#city-map');
const table = document.querySelector('#city-table');
const detail = document.querySelector('#city-detail');
const status = document.querySelector('#city-status');
const freshness = document.querySelector('#city-freshness');
const colors = {interface:'#168aad', service:'#6d4c9f', test:'#d27b2d', knowledge:'#3c8d68'};
const safe = (value, fallback = 'Unavailable') => typeof value === 'string' && value.trim() ? value : fallback;
function showBuilding(building, district) {
  detail.innerHTML = `<h3>${building.path.split('/').pop()}</h3><p class="detail-path">${building.path}</p><dl class="stage-details"><div><dt>Physical LOC</dt><dd>${Number.isFinite(building.loc) ? building.loc.toLocaleString() : 'Unavailable'}</dd></div><div><dt>File size</dt><dd>${Number.isFinite(building.bytes) ? `${Math.round(building.bytes / 1024)} KB` : 'Unavailable'}</dd></div><div><dt>Language / style</dt><dd>${district.language} · ${district.style}</dd></div><div><dt>Dependencies / flow</dt><dd>Snapshot does not include import edges.</dd></div><div><dt>Tests / checks</dt><dd>${safe(building.tests)}</dd></div><div><dt>Status</dt><dd>${safe(building.status)}</dd></div><div><dt>Production relevance</dt><dd>${safe(building.production)}</dd></div></dl>`;
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
      const b = document.createElement('button'); b.type = 'button'; b.className = `building status-${safe(building.status,'unknown').replaceAll(' ','-')}`; b.style.height = `${Math.max(34, Math.sqrt((building.loc || 1) / maxLoc) * 130)}px`; b.style.background = colors[district.style] || '#536878'; b.setAttribute('aria-label', `${building.path}, ${building.loc || 'unknown'} lines, ${safe(building.status)}`); b.title = building.path;
      b.addEventListener('click', () => showBuilding(building, district)); block.append(b);
      const row = document.createElement('tr'); row.innerHTML = `<th scope="row">${building.path}</th><td>${Number.isFinite(building.loc) ? building.loc.toLocaleString() : 'Unavailable'}</td><td>${district.language}</td><td>${safe(building.tests)}</td><td><span class="status-chip ${safe(building.status,'unknown')}">${safe(building.status).toUpperCase()}</span></td><td>${safe(building.production)}</td>`; table.append(row);
    }); zone.append(block); map.append(zone);
  });
  const stamp = safe(payload.generatedAt); freshness.textContent = `Snapshot generated ${stamp}. ${safe(payload.freshness)}. ${safe(payload.note)}`; status.textContent = 'Map ready. Import/API roads and live bug metrics are unavailable in this snapshot.'; status.className = 'inline-status warning';
}
fetch('repository-metrics.json', {headers:{Accept:'application/json'}}).then(response => { if (!response.ok) throw new Error('snapshot unavailable'); return response.json(); }).then(render).catch(() => { status.textContent = 'Metrics snapshot unavailable. No buildings rendered; directory data is not inferred.'; status.className = 'inline-status error'; freshness.textContent = 'Repository metrics could not be loaded.'; });
