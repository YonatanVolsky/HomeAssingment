# Reddit Collector

A local web app: enter a subreddit, and the app collects its newest posts by replaying the
Reddit **mobile app's** HTTP requests, stores them in SQLite, and shows them as a feed of cards.
Design decisions and limitations are in [DESIGN.md](DESIGN.md).

Live collection works: the app fetches real posts from Reddit. Fixture mode
(`COLLECTOR_MODE=fixture`) serves bundled sample data for an offline demo and for the UI's
error states. How the mobile request was reverse-engineered is in
[docs/reddit-mobile-request.md](docs/reddit-mobile-request.md).

## How it fits together

```
browser ──HTTP+JSON──► web service (Node, Express)  ──TCP, one JSON line──► collector (Python)
localhost:5173 (dev)   127.0.0.1:3001                                       127.0.0.1:3002
                       REST API, serves the UI                              term in → collection out
                                                                            Reddit requests, SQLite
```

The collector's line protocol is described in [docs/inner-protocol.md](docs/inner-protocol.md).

## Requirements

- **Python 3.11 or newer** (tested with 3.13) for the collector.
- **Node.js 22 LTS or 24** with npm 10+ for the web service and the frontend.
- Nothing else: SQLite is part of Python, and no Reddit account, keys or secrets are needed.

## Setup (once)

From the repository root, on macOS or Linux:

```bash
python3 -m venv backend/.venv
backend/.venv/bin/pip install -r backend/requirements-dev.txt
npm install                       # installs the frontend and the web service (npm workspaces)
```

On Windows, use `py -m venv backend\.venv` and `backend\.venv\Scripts\pip install -r
backend\requirements-dev.txt`, then start the three parts in three terminals (see
"Running the parts separately").

## Run

```bash
npm run dev                            # live Reddit collection
COLLECTOR_MODE=fixture npm run dev     # offline sample data (demo without hitting Reddit)
```

Open **http://localhost:5173** and enter `ubisoft` or `r/ubisoft`. Stop with `Ctrl+C`.

`npm run dev` starts three processes, labelled in the terminal:

| Label | Part | Address | Notes |
|---|---|---|---|
| `inner` | Collector (Python) | `127.0.0.1:3002` | TCP, local only. Talks to Reddit and the database |
| `server` | Web service (Express) | `http://127.0.0.1:3001` | REST API under `/api` |
| `frontend` | UI (React, Vite) | `http://localhost:5173` | Proxies `/api` to the web service |

The database is a SQLite file, `data/collector.db` (`data/fixture.db` in fixture mode),
created with its schema on first start.

### Running the parts separately

```bash
cd backend && COLLECTOR_MODE=fixture .venv/bin/python -m app.inner   # terminal 1: collector
npm run dev -w server                                                # terminal 2: web service
npm run dev -w frontend                                              # terminal 3: UI
```

### Production-like run

```bash
npm run build                           # builds the UI into frontend/dist
npm start                               # collector + web service; the UI and API on :3001
```

## API

| Request | Meaning |
|---|---|
| `GET /api/posts?term=<subreddit>&freshness=auto` | The subreddit's newest posts: stored if collected in the last 60 s, otherwise collected live first. `auto` is the default |
| `GET /api/posts?term=<subreddit>&freshness=live` | Always collect from Reddit now |
| `GET /api/posts?term=<subreddit>&freshness=stored` | Only what is stored; never calls Reddit (`collection` is `null` if the term was never collected) |
| `GET /api/health` | `{status, db, collectorMode, staleAfterSeconds}` |

A success is `{collection, posts}`. A failure is `{error: {code, message, retryable,
retryAfterSeconds?}, lastGood?}` with a matching HTTP status (400 bad term, 404 subreddit not
found, 429 rate limited with `Retry-After`, 502/504 Reddit problems, 503 collector not running).
`lastGood` is the previous successful feed for the same subreddit, when there is one.

```bash
curl 'http://127.0.0.1:3001/api/posts?term=r/ubisoft&freshness=auto'
```

## Configuration

Every variable is optional; `.env.example` lists them all. They are read from the environment
(for example `COLLECTOR_MODE=fixture npm run dev`); the app does not load `.env` files itself.

Collector (Python):

| Variable | Default | Meaning |
|---|---|---|
| `COLLECTOR_MODE` | `live` | `live` scrapes Reddit; `fixture` serves bundled sample data |
| `DB_PATH` | `./data/collector.db` (live), `./data/fixture.db` (fixture) | SQLite file, relative to the repo root |
| `MAX_POSTS` | `25` | Posts kept per collection (1-100) |
| `COLLECTION_TTL_SECONDS` | `60` | `freshness=auto` serves a collection younger than this (`0` turns it off) |
| `STALE_AFTER_SECONDS` | `600` | The UI suggests refreshing after this |
| `REQUEST_TIMEOUT_MS` | `8000` | Timeout per HTTP request to Reddit |
| `COLLECTION_DEADLINE_MS` | `25000` | Hard limit for a whole collection, including retries |
| `TERM_PROTOCOL` | `reddit-subreddit` | Rules for turning the term into a subreddit name (the only preset). Use a separate `DB_PATH` per protocol |
| `INNER_HOST` / `INNER_PORT` | `127.0.0.1` / `3002` | Where the collector listens |
| `SERVER` | `threadpool` | Collector server implementation (the only preset) |
| `SERVER_THREADS` | `8` | Worker threads for connections (1-64) |
| `INNER_ROUTES` | `collector` | Resource-to-handler preset (the only preset) |
| `LOG_LEVEL` | `info` | `critical`, `error`, `warning`, `info` or `debug` |

Web service (Express):

| Variable | Default | Meaning |
|---|---|---|
| `PORT` / `HOST` | `3001` / `127.0.0.1` | Web service address. If you change `PORT`, also change the proxy in `frontend/vite.config.js` |
| `INNER_HOST` / `INNER_PORT` | `127.0.0.1` / `3002` | Where to reach the collector (shared with the collector's settings) |
| `INNER_TIMEOUT_MS` | `35000` | How long to wait for the collector; above its own 30 s limit |
| `API_ROUTES` | `rest` | REST route preset (the only preset) |

No Reddit credentials are needed: the collector requests the same anonymous token the mobile
app does, at runtime. Nothing secret is stored in the repository.

## Using the app

- Accepted input: `ubisoft`, `r/ubisoft`, `/r/Ubisoft/` or a `reddit.com/r/...` link. Free
  text and partial names are not supported.
- **Collect posts** fetches the newest posts. Repeating the search within 60 seconds shows the
  stored copy, marked **Cached**; **Refresh** always collects again, marked **Live**.
- If a collection fails, the message says why, **Try again** appears when waiting could help
  (after a countdown for rate limits), and the last good feed for that subreddit stays visible.
- The last subreddit you searched is restored from the database when you reload the page.

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
npm test                        # collector (pytest) + web service + frontend (Vitest), offline
npm run lint                    # ESLint for the JavaScript, ruff for the Python
scripts/smoke.sh                # against a running stack (BASE_URL, SMOKE_TERM to override)
scripts/check-compliance.sh     # no browser automation, no official Reddit API
scripts/check-secrets.sh        # no tokens committed
npm run test:live               # opt-in, calls real Reddit
```

## Inspecting the database

```bash
scripts/db-inspect.sh                   # counts, latest runs, newest posts
scripts/db-inspect.sh data/fixture.db
sqlite3 data/collector.db "SELECT term, status, post_count, finished_at FROM collections;"
```

## Project layout

```
backend/              Python: the collector (inner server)
  app/inner/          TCP server, wire protocol, request normalizer, dispatcher, handlers
  app/composition.py  builds everything from configuration (picks the presets)
  app/services/       collection service (cache, de-duplication, failure recording)
  app/terms/          term protocols: normalization steps, presets, the generic normalizer
  app/collector/      field mapping, retry/deadline policy, Reddit requests
  app/db/             connection, schema, repository (all SQL)
  app/contracts.py    the JSON shapes of a collection
  fixtures/           offline sample data
  tests/              pytest
server/               Node: the web service (Express): routes, collector client, HTTP status
frontend/             React (JavaScript/JSX), built with Vite; tests with Vitest
scripts/              smoke, compliance, secret and database helpers
docs/                 inner protocol, Reddit request spec, acceptance record, design specs
plan/                 the original work plan
```

## Re-capturing the Reddit traffic

Not needed to run the app. The capture process (Android emulator, Reddit APK older than
2024.44, HTTP Toolkit) is described in [plan/01-reddit-capture.md](plan/01-reddit-capture.md),
and its result in [docs/reddit-mobile-request.md](docs/reddit-mobile-request.md).

## Troubleshooting

| Problem | Fix |
|---|---|
| `backend/.venv/bin/python: No such file` | Run the setup steps above first |
| `Address already in use` on 3001, 3002 or 5173 | Stop the other process, or change `PORT` / `INNER_PORT` (and the Vite proxy for `PORT`) |
| "The collector service is not running." in the UI | The Python collector is down: check the `[inner]` lines in the terminal |
| "Cannot reach the local server" in the UI | The web service is down: check the `[server]` lines in the terminal |
| "Reddit is limiting requests" | Reddit returned HTTP 429. Wait for the countdown; avoid rapid repeated refreshes |
