#!/usr/bin/env bash
# Shows what is stored: row counts, the latest collection runs, the newest posts.
# Usage: scripts/db-inspect.sh [path-to-db]   (default: data/collector.db)
set -euo pipefail

DB="${1:-${DB_PATH:-data/collector.db}}"
command -v sqlite3 >/dev/null || { echo "sqlite3 CLI not found (it ships with macOS; on Linux: apt install sqlite3)"; exit 1; }
[[ -f "$DB" ]] || { echo "No database at $DB yet. Start the app and run a collection first."; exit 1; }

q() { sqlite3 -header -column "$DB" "$1"; echo; }

echo "== $DB =="
q "SELECT (SELECT COUNT(*) FROM posts) AS posts,
          (SELECT COUNT(*) FROM collections) AS collections,
          (SELECT COUNT(*) FROM collection_posts) AS links;"
echo "-- latest collection runs"
q "SELECT id, term, status, post_count AS posts, COALESCE(error_code, '') AS error, finished_at
   FROM collections ORDER BY id DESC LIMIT 10;"
echo "-- newest posts"
q "SELECT reddit_id, substr(title, 1, 50) AS title, COALESCE(author, '[deleted]') AS author,
          comment_count AS comments, created_at
   FROM posts ORDER BY created_at DESC LIMIT 10;"
