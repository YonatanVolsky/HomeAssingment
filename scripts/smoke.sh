#!/usr/bin/env bash
# End-to-end check against a running backend.
# Usage: scripts/smoke.sh   (env: BASE_URL=http://127.0.0.1:3001, SMOKE_TERM=ubisoft)
set -uo pipefail

BASE_URL="${BASE_URL:-http://127.0.0.1:3001}"
SMOKE_TERM="${SMOKE_TERM:-ubisoft}"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
passed=0
failed=0

ok() { echo "  PASS  $1"; passed=$((passed + 1)); }
bad() { echo "  FAIL  $1"; failed=$((failed + 1)); }

# request METHOD PATH [JSON_BODY] -> writes body to $WORK/body, prints HTTP status
request() {
  local args=(-s -o "$WORK/body" -w '%{http_code}' -X "$1" "$BASE_URL$2")
  [[ $# -ge 3 ]] && args+=(-H 'content-type: application/json' -d "$3")
  curl "${args[@]}" 2>/dev/null || echo 000
}

# json EXPRESSION -> evaluates a Python expression against the last body as `b`
json() { python3 -c "import json,sys; b=json.load(open('$WORK/body')); print($1)" 2>/dev/null; }

echo "Smoke test against $BASE_URL (term: $SMOKE_TERM)"

status=$(request GET /api/health)
if [[ $status == 200 && $(json "b['db']") == ok ]]; then ok "health: db ok"; else bad "health (HTTP $status). Are the web service and the inner server running?"; echo "$failed failed"; exit 1; fi
mode=$(json "b['collectorMode']")
echo "  info  collector mode: $mode"

status=$(request GET "/api/posts?term=")
[[ $status == 400 && $(json "b['error']['code']") == INVALID_TERM ]] && ok "blank term rejected (400 INVALID_TERM)" || bad "blank term (HTTP $status)"

status=$(request GET "/api/posts?term=$SMOKE_TERM&freshness=live")
count=$(json "len(b['posts'])")
if [[ $status == 200 && ${count:-0} -ge 1 ]]; then ok "live collection returned $count posts"
elif [[ $status == 200 ]]; then ok "live collection returned 0 posts (warning: empty subreddit?)"
else bad "live collection (HTTP $status: $(json "b.get('error', {}).get('message')"))"; fi
[[ $(json "(b.get('collection') or {}).get('source')") == live ]] && ok "freshness=live collects live" || bad "live collection source"
ids=$(json "','.join(p['id'] for p in b['posts'])")

status=$(request GET "/api/posts?term=$SMOKE_TERM&freshness=auto")
[[ $status == 200 && $(json "b['collection']['source']") == cache ]] && ok "freshness=auto within TTL served from cache" || bad "cache (HTTP $status)"

status=$(request GET "/api/posts?term=$SMOKE_TERM&freshness=stored")
[[ $status == 200 && $(json "','.join(p['id'] for p in b['posts'])") == "$ids" ]] && ok "freshness=stored returns the same posts" || bad "stored (HTTP $status)"

echo "$passed passed, $failed failed"
[[ $failed -eq 0 ]]
