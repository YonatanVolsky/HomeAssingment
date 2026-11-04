# Acceptance run

Checklist from `plan/06-testing-and-integration.md`. Updated each time it is run.

Runs 1 to 3 predate the current stack (an Express web service in front of the Python
collector, 2026-11-01) and are kept as a record. Run 4 is the current stack, live.

## Run 1: 2026-10-29, offline (fixture mode)

Environment: macOS 14.6.1 (Apple Silicon), Node 24.12.0, npm 11.6.2, SQLite CLI 3.43.2.
Packages: fastify 5.12.7, better-sqlite3 12.11.1, undici 7.30.1, zod 4.6.7, react 19.3.1, vite 6.4.5.

The live Reddit collector is not wired up yet (it waits for the traffic capture,
`plan/01`), so this run used `COLLECTOR_MODE=fixture`. The UI was checked through
automated component tests, not in a real browser.

| # | Check | Result | How |
|---|---|---|---|
| 1 | Fresh clone, follow README, app starts | Partly | `npm install`, `npm run dev`, `npm run build && npm start` all run on this machine. A clean-machine dry run is still to do (plan/07) |
| 2 | Search `ubisoft`: loading, then a feed of cards | Pass (fixture) | `App.test.tsx`; `scripts/smoke.sh` returned 7 posts |
| 3 | Open a card's link: the correct post opens in a new tab | Pass (unit) | `PostCard.test.tsx` checks `href`, `target`, `rel`. Real Reddit links need live mode |
| 4 | Inspect the DB: posts and one collection row | Pass | `scripts/db-inspect.sh` on a seeded database |
| 5 | Reload restores the term: same feed, Cached badge | Pass (unit) | `App.test.tsx` restore test; `server.test.ts` restart test |
| 6 | Repeat within 60 s is cached; Refresh is live; no duplicate posts | Pass | `smoke.sh`; `persistence.test.ts` (2 runs, posts not duplicated) |
| 7 | Empty subreddit: empty state with guidance | Pass (fixture) | Term `empty`; `App.test.tsx` |
| 8 | `r/a`, `bad name!`, blank: validation message; unknown name: not found, no Retry | Pass | `normalizeTerm.test.ts`, `app.test.ts`, `SearchForm.test.tsx`; fixture term `notfound` |
| 9 | Backend stopped: network error state | Pass (unit) | `client.test.ts`, `App.test.tsx`; `smoke.sh` exits 1 when the backend is down |
| 10 | Simulated failure: error banner, previous feed still shown | Pass | Fixture terms `broken`, `timeout`, `ratelimited` (HTTP 429, `Retry-After: 30`); `persistence.test.ts` |
| 11 | Full test suite green | Pass | `npm test`: backend 248, frontend 88 |

Static checks: `scripts/check-compliance.sh` OK, `scripts/check-secrets.sh` OK, `npm run lint` and
`npm run typecheck` clean.

### Still to do

- A run against live Reddit once the capture is done: rows 2, 3, 6 and 10 with real data, and
  `npm run test:live`.
- Look at the UI in a browser at 375 px and 1280 px, keyboard only, in light and dark mode.
- Clean-machine dry run of the README.

## Run 2: 2026-10-29, after the switch to a Python backend (fixture mode)

Python 3.13.1 (FastAPI 0.162.0, uvicorn 0.54.0, httpx 0.28.1, pydantic 2.14.2), Node 24.12.0
for the React build. Same checklist, same results as run 1: `npm test` passes (backend pytest
233, frontend Vitest 88), `scripts/smoke.sh` 6/6 against `python -m app`, `npm run dev`
(proxy) and `npm run build && npm start` (single process) both serve the UI and the API,
compliance and secret checks OK. The "still to do" list above is unchanged.

## Run 3: 2026-10-30, live Reddit

Live collection verified: `pytest -m live` fetched 10 newest posts of r/ubisoft (newest
2026-10-30T05:20:15Z). The scraper uses `curl_cffi` with an Android-client transport
fingerprint, because Reddit's edge 403s a default client (see docs/reddit-mobile-request.md).
Full suite: backend 257 passed + 1 live, frontend 88. Compliance and secret checks OK.

Still to do: look at the UI in a browser (375 px, keyboard, dark mode), a live end-to-end run
through the server and smoke script, and a clean-machine README dry run.

## Run 4: 2026-11-04, current stack, fresh clone, live Reddit

Environment: macOS 14.6 (Apple Silicon), Node 24.12.0, npm 11.6.2, Python 3.13.1. A fresh
`git clone` of `feat/python` (commit 8a08790), set up only with the README's "Setup (once)"
commands.

| # | Check | Result | How |
|---|---|---|---|
| 1 | Fresh clone, follow README, app starts | Pass (same Mac) | Venv, `pip install`, `npm install`; `npm run dev` and `npm run build && npm start` both serve the UI and the API |
| 2 | Search `r/ubisoft`: a feed of cards | Pass (live) | `GET /api/posts?term=r/ubisoft&freshness=live` through the Vite proxy: 25 real posts in 2.0 s, newest first, none missing title, author, comments, time or link |
| 3 | Card links | Pass (live) | Permalinks are `https://www.reddit.com/r/ubisoft/comments/...` |
| 4 | Inspect the DB | Pass | `scripts/db-inspect.sh`: 25 posts, 2 runs (one success, one `NOT_FOUND_SUBREDDIT`), 25 links |
| 6 | Repeat within 60 s is cached | Pass (live) | `freshness=auto` right after: `source: cache`, no Reddit call |
| 8 | Unknown subreddit: not found, no Retry | Pass (live) | A made-up name: HTTP 404 `NOT_FOUND_SUBREDDIT`, `retryable: false` |
| 10 | Every outcome message (fixture) | Pass | Through the proxy: `empty` 200 with 0 posts, `notfound` 404, `ratelimited` 429 + `Retry-After: 30`, `broken` 502, `timeout` 504, `bad name!` and blank 400; a reddit.com link is normalized |
| 11 | Full test suite green | Pass | Collector 407 (+1 live, opt-in), web service 90, frontend 91; lint, compliance and secret checks OK; `scripts/smoke.sh` 6/6 via the proxy |
| 12 | Python versions | Pass | Collector tests pass on 3.11.16, 3.12.14 and 3.13.1 |

Found and fixed in this run: real `curl_cffi` failures were explained wrongly. A hung Reddit
request showed "Reddit is unavailable right now." instead of "Reddit took too long to
respond.", and no network during the token step showed "Could not authenticate with Reddit."
The tests had used `httpx` exceptions, which the app no longer raises. They now use
`curl_cffi`'s, two tests drive the real transport against local sockets, and `httpx` was
removed (collector tests: 411 after the fix).

Still to do: look at the UI in a browser (375 px, keyboard, dark mode); run the README on
another computer and with the Windows steps.
