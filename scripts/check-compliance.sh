#!/usr/bin/env bash
# Mechanical check for the brief's rules: no browser automation, no official Reddit API.
# Scans source and dependency manifests (not docs or markdown, which may name the tools).
# Usage: scripts/check-compliance.sh [repo-root]
set -uo pipefail

ROOT="${1:-$(git rev-parse --show-toplevel 2>/dev/null || pwd)}"
cd "$ROOT" || exit 2

FORBIDDEN_WORDS='selenium|puppeteer|playwright|praw|snoowrap'
FORBIDDEN_URLS='reddit\.com/dev/api|reddit\.com/r/[^ "'"'"']*\.json'
# Reddit hosts the code may mention. Each entry needs a reason; the mobile app's hosts are
# added with a pointer to docs/reddit-mobile-request.md once the capture is done.
ALLOWED_HOSTS=(
  "reddit.com"     # permalink host check in app/collector/mappers.py
  "www.reddit.com" # base for relative permalinks (links shown to the user, not requested)
)

source_files() {
  for dir in backend/app frontend/src scripts; do
    [[ -d $dir ]] && find "$dir" -type f ! -path '*/node_modules/*' ! -path '*/__pycache__/*' \
      ! -name '*.md' ! -name 'check-compliance.sh'
  done
  find . \( -name package.json -o -name 'requirements*.txt' \) -type f \
    ! -path '*/node_modules/*' ! -path '*/.venv/*' | sed 's#^\./##'
}

failed=0
files=()
while IFS= read -r f; do files+=("$f"); done < <(source_files)

if [[ ${#files[@]} -gt 0 ]]; then
  while IFS= read -r hit; do
    echo "check-compliance: forbidden tool: $hit"
    failed=1
  done < <(grep -HnEwi -- "$FORBIDDEN_WORDS" "${files[@]}" 2>/dev/null)

  while IFS= read -r hit; do
    echo "check-compliance: official API / public JSON endpoint: $hit"
    failed=1
  done < <(grep -HnEi -- "$FORBIDDEN_URLS" "${files[@]}" 2>/dev/null)
fi

# Lockfiles list optional peer dependencies that are never installed, so only installed
# packages count there.
if [[ -f package-lock.json ]]; then
  while IFS= read -r hit; do
    echo "check-compliance: installed forbidden package: $hit"
    failed=1
  done < <(grep -nEi "\"node_modules/(@[^/\"]+/)?($FORBIDDEN_WORDS)\"" package-lock.json)
fi

if [[ -d backend/app ]]; then
  while IFS= read -r host; do
    host="${host#.}"
    allowed=0
    for ok in "${ALLOWED_HOSTS[@]}"; do [[ $host == "$ok" ]] && allowed=1; done
    if [[ $allowed -eq 0 ]]; then
      echo "check-compliance: Reddit host '$host' is not on the allow-list (see scripts/check-compliance.sh)"
      failed=1
    fi
  done < <(grep -rhoEi --include='*.py' '[a-z0-9.-]*reddit\.com' backend/app | tr 'A-Z' 'a-z' | sort -u)
fi

if [[ $failed -ne 0 ]]; then
  echo "check-compliance: FAILED"
  exit 1
fi
echo "check-compliance: OK (${#files[@]} files scanned; no browser automation, no official API)"
