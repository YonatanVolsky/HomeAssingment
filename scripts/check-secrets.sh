#!/usr/bin/env bash
# Fails if a file contains a token-shaped value. Matches values, not words, so
# code that builds an Authorization header from a variable passes.
# Usage: scripts/check-secrets.sh [file...]   (default: tracked + staged files)
# Prints file and pattern name only, never the matched value.
set -euo pipefail

PATTERN_NAMES=(
  "JWT-like token"
  "literal Bearer token"
  "quoted credential value"
)
PATTERNS=(
  'eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}'
  'Bearer [A-Za-z0-9._~+/-]{20,}'
  '["'"'"']?(client_secret|access_token|refresh_token|loid|device_id)["'"'"']?[[:space:]]*[:=][[:space:]]*["'"'"'][^"'"'"']{17,}["'"'"']'
)

cd "$(git rev-parse --show-toplevel 2>/dev/null || pwd)"

files=()
if [[ $# -gt 0 ]]; then
  files=("$@")
else
  while IFS= read -r f; do
    case "$f" in
      plan/* | docs/* | scripts/check-secrets.sh | package-lock.json) ;;
      *) [[ -f "$f" ]] && files+=("$f") ;;
    esac
  done < <( { git ls-files; git diff --cached --name-only; } | sort -u )
fi

[[ ${#files[@]} -eq 0 ]] && { echo "check-secrets: no files to scan"; exit 0; }

found=0
for i in "${!PATTERNS[@]}"; do
  while IFS= read -r hit; do
    [[ -n "$hit" ]] || continue
    echo "check-secrets: ${hit}: ${PATTERN_NAMES[$i]}"
    found=1
  done < <(grep -lE -- "${PATTERNS[$i]}" "${files[@]}" 2>/dev/null || true)
done

if [[ $found -ne 0 ]]; then
  echo "check-secrets: FAILED. Remove or scrub the values above (scripts/scrub-fixture.mjs)."
  exit 1
fi
echo "check-secrets: OK (${#files[@]} files scanned)"
