const form = document.querySelector('#search-form');
const queryInput = document.querySelector('#query');
const results = document.querySelector('#results');
const status = document.querySelector('#status');
const count = document.querySelector('#result-count');
const resultsSection = document.querySelector('.results-section');
const statusButton = document.querySelector('#status-button');
const serviceStatus = document.querySelector('#service-status');
const apiBase = '/v1';

function headers() {
  return { Accept: 'application/json' };
}

function announce(message, warning = false) {
  status.hidden = false;
  status.textContent = message;
  status.className = warning ? 'status warning' : 'status';
}

function clearResults() {
  results.replaceChildren();
  count.textContent = '';
}

function renderResults(items) {
  clearResults();
  count.textContent = `${items.length} ${items.length === 1 ? 'result' : 'results'}`;
  items.forEach((hit) => {
    const item = document.createElement('li');
    item.className = 'result';
    const title = document.createElement('h3');
    title.textContent = safeText(hit.title, 'Untitled file');
    const snippet = document.createElement('p');
    snippet.textContent = safeText(hit.snippet, 'No preview available.');
    const metadata = document.createElement('dl');
    metadata.className = 'metadata';
    addMetadata(metadata, 'Scope', 'Synthetic local');
    addMetadata(metadata, 'Source identity', sourceIdentity(hit));
    addMetadata(metadata, 'Source', `Local file · Safe locator · ${safeDisplayValue(hit.source_locator)}`);
    addMetadata(metadata, 'Content version', safeText(hit.source_version));
    addMetadata(metadata, 'Freshness', freshness(hit));
    addMetadata(metadata, 'Provenance', provenance(hit));
    addMetadata(metadata, 'Evidence', evidence(hit));
    addMetadata(metadata, 'Reader status', statusValue(hit, ['reader_status', 'permission_status', 'access_status']));
    addMetadata(metadata, 'Admin status', statusValue(hit, ['admin_status']));
    const state = document.createElement('p');
    state.className = `result-state ${statusClass(hit)}`;
    state.textContent = `Record status: ${statusValue(hit, ['status', 'freshness_status'])}`;
    item.append(title, snippet, state, metadata);
    results.append(item);
  });
}

function safeText(value, fallback = 'Unavailable') {
  return typeof value === 'string' && value.trim() ? value : fallback;
}

function firstValue(value, keys) {
  for (const key of keys) {
    if (typeof value?.[key] === 'string' && value[key].trim()) return value[key].trim();
  }
  return '';
}

function sourceIdentity(hit) {
  return safeDisplayValue(firstValue(hit, ['source_identity', 'source_id', 'source_scope', 'source_key']));
}

function freshness(hit) {
  const value = firstValue(hit, ['freshness_status', 'freshness']);
  return ['fresh', 'warning', 'stale', 'quarantined', 'permission unknown', 'tombstoned'].includes(value)
    ? value : 'Unavailable';
}

function statusValue(hit, keys) {
  return safeText(firstValue(hit, keys));
}

function provenance(hit) {
  const value = hit?.provenance;
  if (Array.isArray(value)) return value.map((link) => typeof link === 'string' ? safeDisplayValue(link) : `${safeText(link?.kind)}: ${safeDisplayValue(link?.identifier)}`).join(' → ') || 'Unavailable';
  return safeDisplayValue(value);
}

function evidence(hit) {
  const value = hit?.evidence;
  if (Array.isArray(value)) return value.map((entry) => typeof entry === 'string' ? safeDisplayValue(entry) : safeDisplayValue(entry?.label || entry?.type)).join(', ') || 'Unavailable';
  return safeDisplayValue(value);
}

function safeDisplayValue(value) {
  if (typeof value !== 'string' || !value.trim()) return 'Unavailable';
  const candidate = value.trim();
  if (candidate.startsWith('/') || candidate.startsWith('\\') || /^[a-zA-Z]:[\\/]/.test(candidate) || /^(file|https?):\/\//i.test(candidate)) return 'Unavailable';
  return candidate;
}

function statusClass(hit) {
  return freshness(hit).replaceAll(' ', '-');
}

function safeSourceName(value) {
  if (typeof value !== 'string' || !value) return 'Unavailable';
  // Never make source values navigable. Show only final file component from file-like values.
  let source = value;
  try {
    if (source.startsWith('file://')) source = decodeURIComponent(new URL(source).pathname);
  } catch (_) {
    return 'Unavailable';
  }
  source = source.replaceAll('\\', '/').split('/').filter(Boolean).pop();
  return source && source !== '.' && source !== '..' ? source : 'Unavailable';
}

function addMetadata(list, label, value) {
  const term = document.createElement('dt');
  term.textContent = label;
  const description = document.createElement('dd');
  description.textContent = value;
  list.append(term, description);
}

async function search(query) {
  resultsSection.setAttribute('aria-busy', 'true');
  announce('Searching…');
  clearResults();
  try {
    const response = await fetch(`${apiBase}/search?q=${encodeURIComponent(query)}`, { headers: headers() });
    if (response.status === 400) {
      announce('Search query is invalid. Enter a bounded query and try again.', true);
      return;
    }
    if (response.status === 403 || response.status === 401) {
      announce('Search is unavailable for this account. No file details were shown.', true);
      return;
    }
    if (response.status === 409) {
      announce('Some results were quarantined or conflicted. No unverified details were shown.', true);
      return;
    }
    if (response.status === 429) {
      announce('Search is rate limited. Retry shortly.', true);
      return;
    }
    if (response.status === 503) {
      announce('Search is degraded or unavailable. No results were shown. Retry later.', true);
      return;
    }
    if (!response.ok) throw new Error(`Search failed (${response.status})`);
    const payload = await response.json();
    const items = Array.isArray(payload) ? payload : payload.items;
    if (!Array.isArray(items)) throw new Error('Unexpected search response');
    renderResults(items);
    if (payload.partial || payload.warning || payload.degraded || payload.complete === false) announce('Search complete with degraded or incomplete coverage. Retry to refresh.', true);
    else announce(items.length ? 'Search complete.' : 'No accessible files matched. Try different terms.');
  } catch (error) {
    announce('Search service is not connected. No results were shown. Try again later.', true);
  } finally {
    resultsSection.setAttribute('aria-busy', 'false');
  }
}

form.addEventListener('submit', (event) => {
  event.preventDefault();
  const query = queryInput.value.trim();
  if (query) search(query);
});

async function checkStatus() {
  statusButton.disabled = true;
  serviceStatus.textContent = 'Checking service status…';
  try {
    const response = await fetch(`${apiBase}/status`, { headers: headers() });
    if (response.status === 401 || response.status === 403) {
      serviceStatus.textContent = 'Status unavailable for this account.';
      return;
    }
    if (response.status === 429) {
      serviceStatus.textContent = 'Status request rate limited. Try again shortly.';
      return;
    }
    if (response.status === 503) {
      serviceStatus.textContent = 'Service is unavailable. Try again later.';
      return;
    }
    if (!response.ok) throw new Error('status failed');
    const data = await response.json();
    const documents = Number.isFinite(data.documents) ? `${data.documents} indexed files` : 'Indexed file count unavailable';
    const removed = Number.isFinite(data.tombstones) && data.tombstones > 0
      ? ` ${data.tombstones} removed ${data.tombstones === 1 ? 'record' : 'records'}.`
      : '';
    serviceStatus.textContent = `Local service available. ${documents}.${removed} Freshness timestamps are not supplied.`;
  } catch (_) {
    serviceStatus.textContent = 'Service is not connected. No status details were shown.';
  } finally {
    statusButton.disabled = false;
  }
}

statusButton.addEventListener('click', checkStatus);

const reportLabels = {
  documents: 'Indexed files', total_documents: 'Indexed files', indexed_documents: 'Indexed files',
  active_documents: 'Available files', available_documents: 'Available files',
  tombstones: 'Removed records', quarantined: 'Quarantined records', quarantine: 'Quarantined records',
  events: 'Events processed', total_events: 'Events processed', processed: 'Events processed',
  projection_lag: 'Projection lag', lag: 'Projection lag', checkpoints: 'Checkpoints',
};

function reportLabel(key) {
  return reportLabels[key] || key.replaceAll('_', ' ').replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function numericValue(value) {
  if (typeof value === 'number' && Number.isFinite(value)) return value;
  if (typeof value === 'string' && value.trim() && Number.isFinite(Number(value))) return Number(value);
  return null;
}

function reportEntries(payload) {
  const source = payload?.report && typeof payload.report === 'object' ? payload.report : payload;
  if (!source || typeof source !== 'object' || Array.isArray(source)) return [];
  const entries = [];
  function visit(value, path = []) {
    if (value && typeof value === 'object' && !Array.isArray(value)) {
      Object.entries(value).forEach(([key, child]) => {
        if (!['stages', 'pipeline', 'flow', 'generated_at', 'updated_at'].includes(key)) visit(child, [...path, key]);
      });
      return;
    }
    if (!path.length || !(numericValue(value) !== null || typeof value === 'string' || typeof value === 'boolean')) return;
    const key = path.at(-1);
    entries.push({ key, label: path.length > 1 ? `${reportLabel(path[0])} · ${reportLabel(key)}` : reportLabel(key), value: numericValue(value) ?? String(value) });
  }
  visit(source);
  return entries;
}

function reportStages(payload, entries) {
  const source = payload?.report && typeof payload.report === 'object' ? payload.report : payload;
  const supplied = source?.stages || source?.pipeline || source?.flow;
  if (Array.isArray(supplied)) {
    return supplied.map((stage) => ({
      label: safeText(stage?.label || stage?.name || stage?.stage, 'Unnamed stage'),
      value: numericValue(stage?.value ?? stage?.count ?? stage?.total),
    })).filter((stage) => stage.value !== null);
  }
  const flowKeys = ['events', 'total_events', 'processed', 'documents', 'total_documents', 'indexed_documents', 'active_documents', 'available_documents', 'tombstones', 'quarantined'];
  return entries.filter((entry) => flowKeys.includes(entry.key) && numericValue(entry.value) !== null).slice(0, 6);
}

function formatMetric(value) {
  const number = numericValue(value);
  return number === null ? safeText(value) : new Intl.NumberFormat().format(number);
}

function renderReport(payload) {
  const entries = reportEntries(payload);
  const stages = reportStages(payload, entries);
  if (!entries.length && !stages.length) throw new Error('Unexpected report response');

  reportKpis.replaceChildren();
  reportBars.replaceChildren();
  reportDetails.replaceChildren();
  const kpis = entries.slice(0, 4);
  kpis.forEach((metric) => {
    const item = document.createElement('div');
    const term = document.createElement('dt');
    const description = document.createElement('dd');
    term.textContent = metric.label;
    description.textContent = formatMetric(metric.value);
    item.append(term, description);
    reportKpis.append(item);
  });

  const greatest = Math.max(...stages.map((stage) => stage.value), 1);
  stages.forEach((stage) => {
    const item = document.createElement('li');
    const label = document.createElement('span');
    const track = document.createElement('span');
    const fill = document.createElement('span');
    const value = document.createElement('strong');
    label.className = 'bar-label'; track.className = 'bar-track'; fill.className = 'bar-fill'; value.className = 'bar-value';
    label.textContent = stage.label;
    fill.style.width = `${Math.max(4, (stage.value / greatest) * 100)}%`;
    track.append(fill);
    value.textContent = formatMetric(stage.value);
    item.append(label, track, value);
    reportBars.append(item);
  });

  entries.forEach((metric) => {
    const row = document.createElement('tr');
    const label = document.createElement('th');
    const value = document.createElement('td');
    label.scope = 'row'; label.textContent = metric.label; value.textContent = formatMetric(metric.value);
    row.append(label, value);
    reportDetails.append(row);
  });
  reportContent.hidden = false;
}

function setReportState(message, kind = '') {
  reportStatus.textContent = message;
  reportStatus.className = `report-status${kind ? ` ${kind}` : ''}`;
}

async function loadReport() {
  reportButton.disabled = true;
  reportPanel.setAttribute('aria-busy', 'true');
  reportContent.hidden = true;
  setReportState('Loading pipeline report…');
  try {
    const response = await fetch(`${apiBase}/report`, { headers: headers() });
    if (response.status === 401 || response.status === 403) {
      setReportState('Pipeline report unavailable for this account.', 'unavailable');
      return;
    }
    if (response.status === 404 || response.status === 501) {
      setReportState('Pipeline report is not available from this service.', 'unavailable');
      return;
    }
    if (response.status === 429) {
      setReportState('Pipeline report is rate limited. Try again shortly.', 'unavailable');
      return;
    }
    if (response.status === 503) {
      setReportState('Pipeline report is temporarily unavailable. Try again later.', 'unavailable');
      return;
    }
    if (!response.ok) throw new Error(`Report failed (${response.status})`);
    renderReport(await response.json());
    setReportState('Pipeline report updated.');
  } catch (_) {
    setReportState('Pipeline report could not be loaded. Check connection and try again.', 'unavailable');
  } finally {
    reportButton.disabled = false;
    reportPanel.setAttribute('aria-busy', 'false');
  }
}

reportButton.addEventListener('click', loadReport);
loadReport();

// A capability is shown as one deterministic radius-one hex cluster. The
// dependency controls stay in a normal details list, so cell labels never
// have to compete with the geometry.
const superhexSlots = [
  [83.138, 48], [166.277, 48],
  [41.569, 120], [124.708, 120], [207.846, 120],
  [83.138, 192], [166.277, 192],
];

function hexPoints(cx, cy, radius = 48) {
  return Array.from({ length: 6 }, (_, index) => {
    const angle = ((60 * index) - 30) * (Math.PI / 180);
    return `${(cx + radius * Math.cos(angle)).toFixed(3)},${(cy + radius * Math.sin(angle)).toFixed(3)}`;
  }).join(' ');
}

document.querySelectorAll('.pipeline-group > .capability-list').forEach((list, groupIndex) => {
  const dependencies = [...list.querySelectorAll(':scope > .capability')];
  if (!dependencies.length) return;

  dependencies.forEach((dependency, dependencyIndex) => {
    dependency.id = `dependency-${groupIndex}-${dependencyIndex}`;
  });

  const parent = list.closest('.pipeline-group')?.querySelector(':scope > .pipeline-parent');
  const title = parent?.querySelector('span')?.textContent || 'Capability';
  const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
  svg.setAttribute('class', 'superhex');
  svg.setAttribute('viewBox', '0 0 249.415 240');
  svg.setAttribute('role', 'img');
  svg.setAttribute('aria-label', `${title}: seven dependency status cells`);
  svg.setAttribute('focusable', 'false');

  superhexSlots.forEach(([cx, cy], slot) => {
    const dependency = dependencies[slot % dependencies.length];
    const cell = document.createElementNS('http://www.w3.org/2000/svg', 'polygon');
    const status = dependency.classList.contains('is-complete') ? 'complete'
      : dependency.classList.contains('is-blocked') ? 'blocked' : 'partial';
    cell.setAttribute('class', `superhex-cell is-${status}`);
    cell.setAttribute('points', hexPoints(cx, cy));
    cell.setAttribute('data-dependency', dependency.id);
    svg.append(cell);
  });

  const detailIndex = document.createElement('details');
  detailIndex.className = 'dependency-index';
  const summary = document.createElement('summary');
  summary.textContent = `Dependencies — ${dependencies.length} named`;
  detailIndex.append(summary, list);
  parent?.insertAdjacentElement('afterend', svg);
  svg.insertAdjacentElement('afterend', detailIndex);
});

document.querySelectorAll('.capability-node, .map-node').forEach((node) => {
  node.addEventListener('click', () => {
    const copy = node.closest('.cluster-copy');
    const capability = copy ? document.querySelector(`#${copy.dataset.owner}`) : node.closest('.dependency-child, .capability, .pipeline-group');
    const pinned = capability.classList.toggle('is-pinned');
    node.setAttribute('aria-expanded', String(pinned));
    if (copy) capability.querySelector('.capability-node')?.setAttribute('aria-expanded', String(pinned));
  });
});
const reportPanel = document.querySelector('.report-panel');
const reportButton = document.querySelector('#report-button');
const reportStatus = document.querySelector('#report-status');
const reportContent = document.querySelector('#report-content');
const reportKpis = document.querySelector('#report-kpis');
const reportBars = document.querySelector('#report-bars');
const reportDetails = document.querySelector('#report-details');
