# Reddit Collector

A local web app: enter a subreddit, the backend collects its newest posts by replaying the
Reddit **mobile app's** HTTP requests, stores them in SQLite, and the browser shows them as a
feed of cards. Design decisions and limitations are in [DESIGN.md](DESIGN.md).

Live collection works: the app fetches real posts from Reddit. Fixture mode
(`COLLECTOR_MODE=fixture`) serves bundled sample data for an offline demo and for the UI's
error states. How the mobile request was reverse-engineered is in
[docs/reddit-mobile-request.md](docs/reddit-mobile-request.md).

## Requirements

- **Python 3.11 or newer** (tested with 3.13) for the backend.
- **Node.js 22 LTS or 24** with npm 10+ for the frontend (React, built with Vite).
- Nothing else: SQLite is part of Python, and no Reddit account, keys or secrets are needed.

## Setup (once)

From the repository root, on macOS or Linux:

```bash
python3 -m venv backend/.venv
backend/.venv/bin/pip install -r backend/requirements-dev.txt
npm install
```

On Windows, use `py -m venv backend\.venv` and `backend\.venv\Scripts\pip install -r
backend\requirements-dev.txt`, then run the backend and frontend in two terminals (see
"Running the two parts separately").

## Run

```bash
npm run dev                            # live Reddit collection
COLLECTOR_MODE=fixture npm run dev     # offline sample data (demo without hitting Reddit)
```

Open **http://localhost:5173** and enter `ubisoft` or `r/ubisoft`. Stop with `Ctrl+C`.

`npm run dev` starts:

| Part | Address | Notes |
|---|---|---|
| Backend (Python, FastAPI) | `http://127.0.0.1:3001` | Local only. API docs at `/api/docs` |
| Frontend (React, Vite) | `http://localhost:5173` | Proxies `/api` to the backend |
| Database (SQLite file) | `data/collector.db` (`data/fixture.db` in fixture mode) | Created on first start, schema applied automatically |

### Running the two parts separately

```bash
cd backend && COLLECTOR_MODE=fixture .venv/bin/python -m app     # terminal 1
npm run dev -w frontend                                          # terminal 2
```

### Single-process run

```bash
npm run build                           # builds the UI into frontend/dist
npm start                               # the backend serves the UI and the API on :3001
```

## Configuration

Every variable is optional; `.env.example` lists them all. They are read from the environment
(for example `PORT=4000 npm run dev`); the app does not load `.env` files itself.

| Variable | Default | Meaning |
|---|---|---|
| `COLLECTOR_MODE` | `live` | `live` scrapes Reddit; `fixture` serves bundled sample data |
| `PORT` / `HOST` | `3001` / `127.0.0.1` | Backend address. If you change `PORT`, also change the proxy in `frontend/vite.config.js` |
| `DB_PATH` | `./data/collector.db` (live), `./data/fixture.db` (fixture) | SQLite file, relative to the repo root |
| `MAX_POSTS` | `25` | Posts kept per collection (1-100) |
| `COLLECTION_TTL_SECONDS` | `60` | A repeat search within this time is served from the database (`0` turns it off) |
| `STALE_AFTER_SECONDS` | `600` | The UI suggests refreshing after this |
| `REQUEST_TIMEOUT_MS` | `8000` | Timeout per HTTP request to Reddit |
| `COLLECTION_DEADLINE_MS` | `25000` | Hard limit for a whole collection, including retries |
| `LOG_LEVEL` | `info` | `critical`, `error`, `warning`, `info` or `debug` |
| `TERM_PROTOCOL` | `reddit-subreddit` | Rules for turning the search term into a subreddit name; only `reddit-subreddit` exists. Use a separate `DB_PATH` per protocol |

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
npm test                        # backend (pytest) + frontend (Vitest), offline, a few seconds
npm run lint                    # ESLint for the UI, ruff for the backend
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
backend/              Python: FastAPI app, collector, SQLite repository
  app/api.py          HTTP endpoints and error responses
  app/services/       collection service (cache, de-duplication, failure recording)
  app/terms/          term protocols: normalization steps, presets, the generic normalizer
  app/collector/      field mapping, retry/deadline policy, Reddit requests
  app/db/             connection, schema, repository (all SQL)
  app/contracts.py    the JSON shapes sent to the browser
  fixtures/           offline sample data
  tests/              pytest
frontend/             React (JavaScript/JSX), built with Vite; tests with Vitest
scripts/              smoke, compliance, secret and database helpers
docs/                 acceptance record, Reddit request spec (after capture)
plan/                 the work plan
```

## Re-capturing the Reddit traffic

Not needed to run the app. The capture process (Android emulator, Reddit APK older than
2024.44, HTTP Toolkit) is described in [plan/01-reddit-capture.md](plan/01-reddit-capture.md);
its result will be documented in `docs/reddit-mobile-request.md`.

## Troubleshooting

| Problem | Fix |
|---|---|
| `backend/.venv/bin/python: No such file` | Run the setup steps above first |
| `Address already in use` on 3001 or 5173 | Stop the other process, or set `PORT` (and update the Vite proxy) |
| "Cannot reach the local server" in the UI | The backend is not running or crashed: check the `[backend]` lines in the terminal |
| "Reddit is limiting requests" | Reddit returned HTTP 429. Wait for the countdown; avoid rapid repeated refreshes |
