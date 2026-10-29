# Reddit Collector

A local web app: enter a subreddit, the backend collects its newest posts by replaying the
Reddit **mobile app's** HTTP requests, stores them in SQLite, and the browser shows them as a
feed of cards. Design decisions and limitations are in [DESIGN.md](DESIGN.md).

> **Status:** the app, database, API, UI and tests are complete. The Reddit mobile request
> itself is still being captured (see [plan/01](plan/01-reddit-capture.md)), so until then
> live mode returns a clear "not available yet" error. **Use fixture mode** (below) to run
> the full flow with bundled sample data.

## Requirements

- **Node.js 22 LTS or 24** (`.nvmrc` says 22) and npm 10 or newer.
- Nothing else: no database server, no Docker, no Reddit account, keys or environment
  variables. SQLite is embedded through `better-sqlite3`, which downloads a prebuilt binary
  for your platform. If that download fails, a C/C++ toolchain is needed to build it
  (macOS: `xcode-select --install`; Debian/Ubuntu: `sudo apt install build-essential python3`).

## Quick start

```bash
git clone <repo-url> reddit-collector
cd reddit-collector
nvm use                 # optional, if you use nvm
npm install
COLLECTOR_MODE=fixture npm run dev     # offline sample data (works today)
# npm run dev                          # live Reddit, once the capture is wired up
```

Open **http://localhost:5173** and enter `ubisoft` or `r/ubisoft`.

`npm run dev` starts:

| Process | Address | Notes |
|---|---|---|
| Backend (Fastify) | `http://127.0.0.1:3001` | Local only. Logs as JSON to the terminal |
| Frontend (Vite) | `http://localhost:5173` | Proxies `/api` to the backend |
| Database (SQLite file) | `data/collector.db` (`data/fixture.db` in fixture mode) | Created on first start, schema applied automatically |

Stop with `Ctrl+C`.

### Single-process run

```bash
npm run build
COLLECTOR_MODE=fixture npm start      # serves the built UI and the API on http://127.0.0.1:3001
```

## Configuration

Every variable is optional; copy `.env.example` to see them all. The backend reads them from
the environment (for example `PORT=4000 npm run dev`).

| Variable | Default | Meaning |
|---|---|---|
| `COLLECTOR_MODE` | `live` | `live` scrapes Reddit; `fixture` serves bundled sample data |
| `PORT` / `HOST` | `3001` / `127.0.0.1` | Backend address. If you change `PORT`, also change the proxy in `frontend/vite.config.ts` |
| `DB_PATH` | `./data/collector.db` (live), `./data/fixture.db` (fixture) | SQLite file, relative to the repo root |
| `MAX_POSTS` | `25` | Posts kept per collection (1-100) |
| `COLLECTION_TTL_SECONDS` | `60` | A repeat search within this time is served from the database (`0` turns it off) |
| `STALE_AFTER_SECONDS` | `600` | The UI suggests refreshing after this |
| `REQUEST_TIMEOUT_MS` | `8000` | Timeout per HTTP request to Reddit |
| `COLLECTION_DEADLINE_MS` | `25000` | Hard limit for a whole collection, including retries |
| `LOG_LEVEL` | `info` | `fatal`, `error`, `warn`, `info`, `debug`, `trace` or `silent` |

No Reddit credentials are needed: the collector requests the same anonymous token the mobile
app does, at runtime. Nothing secret is stored in the repository.

## Using the app

- Accepted input: `ubisoft`, `r/ubisoft`, `/r/Ubisoft/` or a `reddit.com/r/...` link. Free
  text and partial names are not supported.
- **Collect posts** fetches the newest posts. Repeating the search within 60 seconds shows the
  stored copy, marked **Cached**; **Refresh** always collects again, marked **Live**.
- If a collection fails, the message says why, **Try again** appears when waiting could help
  (after a countdown for rate limits), and the last good feed for that subreddit stays visible.
- The last subreddit you searched is restored when you reload the page.

In fixture mode these subreddit names simulate each outcome:

| Name | Result |
|---|---|
| any valid name | 7 sample posts |
| `empty` | No posts (empty state) |
| `notfound` | Subreddit not found (no retry) |
| `ratelimited` | Rate limited, retry after a 30 s countdown |
| `broken` | Reddit unavailable |
| `timeout` | Reddit took too long |

## Tests and checks

```bash
npm test                        # backend + frontend, offline (a few seconds)
npm run lint
npm run typecheck
scripts/smoke.sh                # against a running backend (BASE_URL, SMOKE_TERM to override)
scripts/check-compliance.sh     # no browser automation, no official Reddit API
scripts/check-secrets.sh        # no tokens committed
npm run test:live               # opt-in, calls real Reddit (after the capture)
```

## Inspecting the database

```bash
scripts/db-inspect.sh                   # counts, latest runs, newest posts
scripts/db-inspect.sh data/fixture.db
sqlite3 data/collector.db "SELECT term, status, post_count, finished_at FROM collections;"
```

## Project layout

```
backend/            Fastify API, collector, SQLite repository (TypeScript)
  src/collector/    term validation, field mapping, retry/deadline policy, Reddit requests
  src/db/           connection, schema, repository
  src/services/     collection service (cache, de-duplication, failure recording)
  src/routes/       HTTP endpoints
  fixtures/         offline sample data
frontend/           React + Vite UI
packages/contracts/ API types shared by backend and frontend
scripts/            smoke, compliance, secret and database helpers
docs/               acceptance record, Reddit request spec (after capture)
plan/               the work plan
```

## Re-capturing the Reddit traffic

Not needed to run the app. The capture process (Android emulator, Reddit APK older than
2024.44, HTTP Toolkit) is described in [plan/01-reddit-capture.md](plan/01-reddit-capture.md);
its result will be documented in `docs/reddit-mobile-request.md`.

## Troubleshooting

| Problem | Fix |
|---|---|
| `EADDRINUSE` on 3001 or 5173 | Another process uses the port: stop it, or set `PORT` (and update the Vite proxy) |
| `npm install` fails building `better-sqlite3` | Use Node 22 or 24 (prebuilt binaries exist for them), or install the toolchain above |
| "Cannot reach the local server" in the UI | The backend is not running or crashed: check the `[backend]` lines in the terminal |
| "Live Reddit collection is not available yet" | Expected until the capture is done; use `COLLECTOR_MODE=fixture` |
| "Reddit is limiting requests" | Reddit returned HTTP 429. Wait for the countdown; avoid rapid repeated refreshes |
