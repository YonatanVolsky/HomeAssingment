# Design notes

## Request path

```
Browser (React)
  └─ GET /api/posts?term=r/Ubisoft&freshness=auto   via the Vite dev proxy (same origin, no CORS)
Web service: Express on 127.0.0.1:3001             server/src/app.js
  ├─ route preset (API_ROUTES=rest) turns the request into a command
  │    {"v":1,"command":"GET","resource":"posts","args":{"term":"r/Ubisoft","freshness":"auto"}}
  └─ innerClient: one JSON line over TCP, one JSON line back → HTTP status + JSON
Collector: Python on 127.0.0.1:3002                backend/app/inner/
  ├─ ThreadPoolServer      one request line per connection, from a pool of worker threads
  ├─ RequestNormalizer     validates the message; term protocol: "r/Ubisoft", links → "ubisoft"
  ├─ Dispatcher            resource "posts" → PostsHandler.get(args)   (INNER_ROUTES preset)
  └─ PostsHandler          runs on the one event-loop thread (LoopThread):
       auto → CollectionService.collect   live → collect(force)   stored → get_posts
       CollectionService                  backend/app/services/collection_service.py
         ├─ repository.get_fresh_success   a run younger than 60 s → return it as "cache"
         ├─ in-flight tasks         a run already going for this term → wait for it
         ├─ RedditCollector         deadline, retries, token refresh
         │    ├─ TokenProvider      the app's anonymous token, cached until shortly before expiry
         │    └─ ListingSource      the app's "subreddit, sorted by New" request, parsed and validated
         └─ repository.record_success      one SQLite transaction: upsert posts, insert run, link them
       response read back from SQLite (what you see is what was stored)
Browser: state machine → cards, empty state or error banner
```

## Decisions

| Decision | Why | Trade-off |
|---|---|---|
| Two servers: Express web service + Python collector | The web service owns HTTP (routes, status codes, the UI); the collector does the brief's job (term in, collection out) and owns Reddit and the database. HTTP never reaches Python and domain rules never reach Node, so each side can change or be replaced alone | Three processes in development; a TCP hop per request (on localhost) |
| Python for the collector | The usual language for scraping. Reddit's edge filters clients by their TLS fingerprint and Python has `curl_cffi` to imitate the app's; Node has no mature equivalent | Two toolchains (Python and Node) |
| A line-based JSON protocol over TCP, one request per connection (`docs/inner-protocol.md`) | Simple to implement and to test by hand with `nc`; framing is a newline; no shared state between requests | A TCP handshake per request (negligible on localhost); no streaming |
| A thread pool plus one event loop in the collector | Worker threads serve connections; every service, Reddit and SQLite call runs on one asyncio loop thread, so the existing async code (shared in-flight runs, one token refresh) keeps its guarantees and SQLite is used from one thread | Database and Reddit work is not parallel across threads (fine for one local user) |
| `GET` with a `freshness` argument instead of POST | From the user's view, reading a feed is a GET; `auto`/`live`/`stored` covers search, Refresh and reload-restore with one command | `auto`/`live` can collect and write, so it is not a "safe" GET in HTTP terms; `Cache-Control: no-store` stops caches and prefetchers repeating it |
| React frontend in plain JavaScript (JSX) | The UI needs a browser framework; plain JS keeps it readable without TypeScript. `src/api/types.js` documents the API shapes | No compile-time type checks in the UI; the tests cover behavior |
| Express 5 for the web service | Small, well known, and enough for two routes plus static files; tests call it in-process with supertest | No generated API docs (FastAPI's `/api/docs` went with FastAPI); the README documents the API |
| SQLite (Python's built-in `sqlite3`) | Nothing to install or start; explicit transactions are simple | One writer at a time (fine locally) |
| Three tables: `posts`, `collections`, `collection_posts` | A feed is "the posts of the latest successful run for a term". Posts are stored once even when several terms return them, and history explains itself (failed runs keep their error code) | One join per feed read |
| Synchronous request, no job queue | A collection takes seconds; a queue adds polling and state for no user benefit here | A slow Reddit holds the request open (bounded by the deadlines below) |
| The cache is the database | One source of truth that survives restarts; the UI always knows how old data is | Cached counts can be up to a minute old |
| Validation at both edges | Malformed commands are rejected (`INVALID_REQUEST`) and unexpected Reddit responses fail loudly instead of storing half-empty posts | Schema must change if Reddit changes its response |
| Presets chosen at startup (`TERM_PROTOCOL`, `SERVER`, `INNER_ROUTES`, `API_ROUTES`) | Which rules, server and routes are used is a deployment choice (environment, e.g. Docker); every selectable option is defined and tested in code, and `app/composition.py` is the one place that picks | Each has one preset today; config can only pick presets, not assemble new ones |
| Term rules are a chain of steps (a protocol), chosen at startup with `TERM_PROTOCOL` | The normalizer is generic and never changes; a new set of input rules is new steps plus one preset in `app/terms/presets.py`, picked by whoever deploys the app. The service depends only on a `normalize(raw) -> str` interface | Config can only pick presets defined in code, not assemble chains |
| Fixture mode with its own database file | Demo and development without Reddit; sample data can never mix with real data | Sample data is synthetic |

### Design principles applied (SOLID)

- **Single responsibility:** `RedditCollector` only knows reliability (deadline, retry, token
  refresh); the Reddit request and parser live behind `ListingSource`; all SQL lives in
  `Repository`; `CollectionService` only orchestrates; the Express app only translates HTTP;
  the collector's server only frames bytes, the request normalizer only validates and
  normalizes, the dispatcher only routes, and each handler serves one resource.
- **Open/closed and dependency inversion:** high-level code depends on small `Protocol`
  interfaces (`Collector`, `ListingSource`, `TokenSource`, `Clock`, `Normalizer`,
  `CommandHandler`) passed in through
  constructors. Swapping live and fixture collectors, or Reddit changing its request, touches
  one implementation. The same seams let every test run offline with a fake clock and a real
  in-memory SQLite database.
- **Interface segregation:** the token provider is consumed through a two-method
  `TokenSource`.
- **One rule, one place:** a single error table (`app/errors.py`) decides whether the collector
  retries and whether the UI offers "Try again"; HTTP status lives only in the web service's
  table (`server/src/errors.js`). A test asserts the retry behavior matches it for every code.

## Reliability

- **Timeouts, each layer longer than the one below:** 8 s per Reddit request; a 25 s
  deadline for the whole collection (`asyncio.timeout`, covering token, retries and refresh);
  a collector worker waits at most 30 s; the web service waits 35 s for the collector; the
  browser waits 40 s. So the layer that knows most (and can attach `lastGood`) always answers
  first. The web service refuses to start with an `INNER_TIMEOUT_MS` outside that order. A connection must deliver its request line within 5 s in total, so a slow client
  cannot hold a worker.
- **Retries:** network errors, timeouts and 5xx are retried twice with exponential backoff and
  jitter, but never past the deadline. 429 is never retried (it makes rate limiting worse) and
  its `Retry-After` reaches the UI as a countdown. A 401/403 triggers one token refresh, and
  only the rejected token is discarded.
- **Concurrency:** requests for the same term share one collection task; the shared token
  refresh has its own timeout. Both are wrapped in `asyncio.shield`, so one request giving up
  (deadline or closed browser tab) never cancels work other requests are waiting on.
- **No duplicates:** posts are upserted by Reddit id.
- **Failures:** every failed run is recorded with its error code and never replaces the last
  good feed, which the API returns next to the error.
- **Writes are atomic:** posts, the run row and its links are one transaction.
- **Overload:** up to 64 connections may wait for a free collector thread; more get `BUSY`
  (503) at once instead of piling up.
- **Stopping:** Ctrl+C gives running requests 2 s, then both servers exit; committed
  transactions make that safe.

## Security

Backend bound to `127.0.0.1`; no secrets in the repository (`scripts/check-secrets.sh`);
request headers are never logged; error responses never include causes or tracebacks; SQL uses
bound parameters only; the static file route cannot serve files outside the build folder;
React escapes all text and links are rendered only for `https://` reddit.com URLs.

## Compliance with the brief

No browser automation and no official API: `scripts/check-compliance.sh` fails on browser
automation or Reddit API client packages (in code, `package.json` or `requirements*.txt`), on
Reddit's public `.json` endpoints, and on any Reddit host in the backend that is not on a
commented allow-list. The mobile app's hosts are added to that list with a pointer to
`docs/reddit-mobile-request.md`, which explains why they are app traffic rather than the
developer API.

## Known limitations

- Subreddit names only: no free-text search, no partial-name matching.
- Stored runs are keyed by the normalized term only. Switching `TERM_PROTOCOL` while keeping the
  same database file can serve a run stored under the old protocol for the same term (from the
  cache, or as the restored feed). Use a separate `DB_PATH` per protocol.
- One page of newest posts (up to `MAX_POSTS`); no pagination or other sort orders.
- Counts are as of the last collection; no background refresh.
- No retention pruning: the database grows by one run per live collection (posts are
  de-duplicated, so a local demo stays small).
- The in-flight de-duplication is per process (correct for one local collector).
- All database and Reddit work runs on one event-loop thread; the worker pool adds
  concurrency for connections and waiting, not for database writes.
- Both servers bind to localhost only. A connection refused as `BUSY` is answered on the
  accepting thread, which may then wait up to 0.5 s for that client to hang up.
- No authentication or rate limiting on our own API or between the web service and the
  collector (local tool, both on localhost).
- `npm run dev` uses macOS/Linux paths for the Python virtual environment; Windows users run
  the three parts in separate terminals.
- Depends on an old app version's unofficial endpoints, which Reddit can change or block, and
  on the `chrome_android` transport fingerprint remaining accepted by Reddit's edge.

## How live collection works (and the fingerprint)

The app's requests are reverse-engineered in `docs/reddit-mobile-request.md`. One wrinkle:
replaying them from a default Python HTTP client returns 403 from Reddit's edge, which
fingerprints the TLS/HTTP-2 handshake to tell a real app from a script. The default transport
(`CurlCffiTransport`) therefore uses `curl_cffi` with an Android-client profile, so our
connection looks like the app's at the transport layer. It is still a direct HTTP request we
build ourselves — no browser, no automation — which keeps it within Appendix A's rules.

## What is not finished

- A browser check of the UI (375 px, keyboard only, dark mode).
- The README was followed on a fresh clone on macOS (2026-11-04, `docs/acceptance.md` run 4),
  but not on another computer, and the Windows steps have not been run.

## With more time

Free-text search inside a subreddit, pagination, retention pruning and real migrations,
scheduled re-collection, thumbnails and media type on cards, a browser end-to-end test, and a
scheduled contract test against live Reddit to catch format changes early.

## AI usage

Built with Claude Code: planning, implementation (test first for every module), a review of
the whole branch by a separate reviewer, and a port of the backend from TypeScript to Python
with the same tests. Every decision that deviated from the plan was recorded with its reason.
Tests, builds, the smoke script and the HTTP checks were run and read, not assumed.
