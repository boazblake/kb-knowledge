#!/usr/bin/env bash
set -euo pipefail

# Dependency-free BDD smoke suite. Requires Python 3 and agent-browser.
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
PORT=$((18000 + ($$ % 1000)))
SESSION="frontend-bdd-$$"
FAIL_SESSION="frontend-bdd-fail-$$"
SERVER_LOG=$(mktemp)
PASS=0
FAIL=0

cleanup() {
  kill "$SERVER_PID" 2>/dev/null || true
  agent-browser --session "$SESSION" close >/dev/null 2>&1 || true
  agent-browser --session "$FAIL_SESSION" close >/dev/null 2>&1 || true
  rm -f "$SERVER_LOG"
}
trap cleanup EXIT

if ! command -v agent-browser >/dev/null 2>&1; then
  printf 'SKIP: agent-browser is required\n'
  exit 2
fi

python3 -m http.server "$PORT" --bind 127.0.0.1 --directory "$ROOT" >"$SERVER_LOG" 2>&1 &
SERVER_PID=$!
for _ in $(seq 1 50); do
  if curl -fsS "http://127.0.0.1:$PORT/frontend/project-visualization.html" >/dev/null; then
    break
  fi
  sleep 0.1
done

URL="http://127.0.0.1:$PORT/frontend/project-visualization.html"
agent-browser --session "$SESSION" open "$URL" >/dev/null
agent-browser --session "$SESSION" wait --load networkidle >/dev/null

check() {
  local name=$1 result=$2
  if [[ "$result" == *true* ]]; then
    PASS=$((PASS + 1)); printf 'PASS: %s\n' "$name"
  else
    FAIL=$((FAIL + 1)); printf 'FAIL: %s (%s)\n' "$name" "$result"
  fi
}

eval_page() {
  agent-browser --session "$SESSION" eval --stdin
}

check 'Given page is served over HTTP, When loaded, Then title and status render' \
  "$(eval_page <<'EOF'
JSON.stringify(location.protocol === 'http:' && document.title === 'Project visualization' && document.documentElement.dataset.statusValidated === 'true' && document.body.innerText.includes('Production NO-GO'))
EOF
)"

# E2E-009/P4-11 metadata assertion: mode, qualification, committed hashes, and
# prior-recorded/dirty-worktree scope remain visible and internally consistent.
check 'Given reference metadata, When page renders, Then mode, qualification, commit, and scope agree' \
  "$(eval_page <<'EOF'
const text = document.body.innerText;
JSON.stringify(text.includes('MOCK / REFERENCE') && text.includes('production_qualification=false') && text.includes('1656b0e') && text.includes('development/mock scope only') && text.includes('397911e') && text.includes('uncommitted changes excluded'));
EOF
)"

# E2E-009 assertion: controls and network remain read-only/no-mutation.
check 'Given read-only visualization, When controls are enumerated, Then no mutation control exists' \
  "$(eval_page <<'EOF'
const controls = [...document.querySelectorAll('button, input, select, textarea, form')];
JSON.stringify(controls.every(node => node.tagName === 'BUTTON' && node.type === 'button' && !/delete|save|submit|mutat|write|edit/i.test(node.textContent + node.getAttribute('aria-label'))));
EOF
)"

NETWORK=$(agent-browser --session "$SESSION" network requests 2>&1 || true)
if [[ "$NETWORK" =~ (POST|PUT|PATCH|DELETE) ]]; then
  check 'When page loads, Then no mutation network request fires' false
else
  check 'When page loads, Then no mutation network request fires' true
fi

check 'Given hub sections, When page renders, Then blueprint, hexagons, roadmap, and observations exist' \
  "$(eval_page <<'EOF'
JSON.stringify(document.querySelector('#flow-svg')?.querySelectorAll('.flow-node').length > 0 && document.querySelectorAll('.hex').length > 0 && document.querySelector('#roadmap-lanes')?.children.length > 0 && document.querySelector('#p4-ledger')?.rows.length > 0);
EOF
)"

agent-browser --session "$SESSION" focus '#flow-nodes .flow-node:first-child' >/dev/null
agent-browser --session "$SESSION" press Enter >/dev/null
# E2E-010 assertion: keyboard activation exposes observable detail.
check 'Given keyboard focus, When Enter activates blueprint node, Then detail becomes observable' \
  "$(eval_page <<'EOF'
JSON.stringify(document.activeElement?.getAttribute('role') === 'button' && document.querySelector('#flow-detail').innerText.includes('Local files'));
EOF
)"

# E2E-010 assertion: accessible alternatives expose table/list content.
check 'Given visual alternatives, When accessible content is inspected, Then tables and lists contain rows' \
  "$(eval_page <<'EOF'
JSON.stringify(document.querySelectorAll('table tbody tr').length >= 4 && document.querySelectorAll('details.accessible ul li').length >= 4 && document.querySelectorAll('details.accessible table').length >= 2);
EOF
)"

# E2E-009/E2E-010 assertion: stale state remains explicit and safe.
check 'Given stale reference state, When page renders, Then stale status remains explicit and safe' \
  "$(eval_page <<'EOF'
JSON.stringify(document.documentElement.dataset.snapshotState === 'stale' && document.body.innerText.includes('stale') && document.body.innerText.includes('not live production'));
EOF
)"

# E2E-010 assertion: failed snapshot delivery exposes safe empty state.
# Abort shared status script to model failed snapshot delivery. App must keep its
# shell usable and expose safe empty-state text instead of throwing.
agent-browser --session "$FAIL_SESSION" network route '**/visualization-status.js' --abort >/dev/null
agent-browser --session "$FAIL_SESSION" open "$URL" >/dev/null
agent-browser --session "$FAIL_SESSION" wait --load networkidle >/dev/null
FAILED=$(agent-browser --session "$FAIL_SESSION" eval --stdin <<'EOF'
JSON.stringify(document.documentElement.dataset.snapshotState === 'failed' && document.querySelector('#p4-status').innerText.includes('unavailable') && document.querySelector('#p4-ledger').innerText.includes('unavailable'));
EOF
)
check 'Given failed snapshot delivery, When page renders, Then safe empty state is visible' "$FAILED"

printf 'BDD browser tests: %d passed, %d failed\n' "$PASS" "$FAIL"
(( FAIL == 0 ))
