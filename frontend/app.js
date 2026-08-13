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
