# Design notes

## Request path

```
Browser (React)
  └─ POST /api/collections {term}         via the Vite dev proxy (same origin, no CORS)
Fastify on 127.0.0.1:3001
  └─ CollectionService
       ├─ normalizeTerm          "r/Ubisoft", links → "ubisoft"; invalid → 400, Reddit never called
       ├─ repository.getFreshSuccess   a run younger than 60 s → return it as "cache"
       ├─ in-flight map          a run already going for this term → wait for it
       ├─ RedditCollector        deadline, retries, token refresh
       │    ├─ TokenProvider     the app's anonymous token, cached until shortly before expiry
       │    └─ ListingSource     the app's "subreddit, sorted by New" request, parsed and validated
       └─ repository.recordSuccess     one SQLite transaction: upsert posts, insert run, link them
  └─ response read back from SQLite (what you see is what was stored)
Browser: state machine → cards, empty state or error banner
```

## Decisions

| Decision | Why | Trade-off |
|---|---|---|
| TypeScript on Node 22+ for everything | One language, one `npm install`; shared API types in `packages/contracts` | Node 20 is end of life, so 22 is the floor |
| Fastify | `app.inject()` tests every endpoint without a port or network | Less familiar than Express |
| SQLite (`better-sqlite3`) | Nothing to install or start; synchronous transactions are simple | Native module; prebuilt binaries cover LTS Node versions |
| Three tables: `posts`, `collections`, `collection_posts` | A feed is "the posts of the latest successful run for a term". Posts are stored once even when several terms return them, and history explains itself (failed runs keep their error code) | One join per feed read |
| Synchronous request, no job queue | A collection takes seconds; a queue adds polling and state for no user benefit here | A very slow Reddit holds the request open (bounded by the 25 s deadline) |
| The cache is the database | One source of truth that survives restarts; the UI always knows how old data is | Cached counts can be up to a minute old |
| zod at both edges | Bad requests are rejected and unexpected Reddit responses fail loudly instead of storing half-empty posts | Schema must change if Reddit changes its response |
| Fixture mode with its own database file | Demo and development without Reddit; sample data can never mix with real data | Sample data is synthetic |

### Design principles applied (SOLID)

- **Single responsibility:** `RedditCollector` only knows reliability (deadline, retry, token
  refresh); the Reddit request and parser live behind `ListingSource`; storage lives in the
  repository; `CollectionService` only orchestrates.
- **Open/closed and dependency inversion:** high-level code depends on small interfaces
  (`Collector`, `ListingSource`, `TokenSource`, `CollectionRepository`, `Clock`, `Logger`)
  passed in through constructors. Swapping live and fixture collectors, or Reddit changing its
  request, touches one implementation. The same seams let every test run offline with a fake
  clock and real SQLite in memory.
- **Interface segregation:** the token provider is consumed through a two-method
  `TokenSource`; health only needs `ping()` from the repository.
- **One rule, one place:** a single error table decides HTTP status, whether the collector
  retries, and whether the UI offers "Try again". A test asserts the retry behavior matches it.

## Reliability

- **Timeouts:** 8 s per request and a 25 s deadline for the whole collection (token, retries,
  refresh). The browser waits 35 s, so the backend always answers first.
- **Retries:** network errors, timeouts and 5xx are retried twice with exponential backoff and
  jitter, but never past the deadline. 429 is never retried (it makes rate limiting worse) and
  its `Retry-After` reaches the UI as a countdown. A 401/403 triggers one token refresh.
- **De-duplication:** concurrent requests for the same term share one Reddit call; posts are
  upserted by Reddit id, so re-collecting never duplicates them.
- **Failures:** every failed run is recorded with its error code and never replaces the last
  good feed, which the API returns next to the error.
- **Writes are atomic:** posts, the run row and its links are one transaction.

## Security

Backend bound to `127.0.0.1`; no secrets in the repository (`scripts/check-secrets.sh`);
`authorization`, `cookie` and token fields redacted from logs; error responses never include
causes or stack traces; SQL uses bound parameters only; React escapes all text and links are
rendered only for `https://` reddit.com URLs.

## Compliance with the brief

No browser automation and no official API: `scripts/check-compliance.sh` fails on browser
automation or Reddit API client packages, on Reddit's public `.json` endpoints, and on any
Reddit host in the backend that is not on a commented allow-list. The mobile app's hosts are
added to that list with a pointer to `docs/reddit-mobile-request.md`, which explains why they
are app traffic rather than the developer API.

## Known limitations

- **Live collection is not finished** (see below).
- Subreddit names only: no free-text search, no partial-name matching.
- One page of newest posts (up to `MAX_POSTS`); no pagination or other sort orders.
- Counts are as of the last collection; no background refresh.
- No retention pruning: the database grows by one run per live collection (posts are
  de-duplicated, so a local demo stays small).
- The in-flight de-duplication is per process (correct for one local server).
- No authentication or rate limiting on our own API (local tool).
- Depends on an old app version's unofficial endpoints, which Reddit can change or block.

## What is not finished

- **The Reddit mobile request.** The capture (emulator, old APK, HTTP Toolkit) has not been
  done yet, so `backend/src/collector/reddit/mobileApi.ts` is a placeholder that reports
  "not available yet". Everything around it (token caching, retries, deadline, error
  classification, mapping and validation helpers, storage, API, UI) is built and tested.
  Remaining: the request builders, the response schema and parser from real responses, raw
  fixtures, and the live test.
- A browser check of the UI (375 px, keyboard only, dark mode) and a clean-machine dry run.

## With more time

Free-text search inside a subreddit, pagination, retention pruning and real migrations,
scheduled re-collection, thumbnails and media type on cards, a browser end-to-end test, and a
scheduled contract test against live Reddit to catch format changes early.

## AI usage

Built with Claude Code: planning, implementation (test first for every module) and review.
Every decision that deviated from the plan was recorded with its reason. Tests, builds, the
smoke script and the curl checks were run and read, not assumed.
