# 04 Backend API

## Goal and dependencies

The local HTTP server that the frontend talks to. It validates requests,
orchestrates cache, collector, and database, and turns every failure into a safe
structured error. Depends on `00`, `03` and the `Collector` interface from `02`
(it can run against the fixture collector before the real scraper works).

## Request path

```
Browser ─► Vite dev proxy ─► Fastify :3001
                               POST /api/collections
                                 └► CollectionService
                                      ├► normalizeTerm            (02)
                                      ├► in-flight map
                                      ├► repository.getFreshSuccess (03)
                                      ├► collector.collect          (02) ─► Reddit mobile
                                      └► repository.recordSuccess   (03) ─► SQLite
                               GET /api/posts, GET /api/health
```

## Step-by-step plan

1. Work on `feat/app`.
2. **`buildApp(deps)`** in `app.ts`: creates the Fastify instance from injected
   dependencies (`repository`, `collector`, `config`, `clock`), so tests need no
   network and no port. `server.ts` is the thin entrypoint that wires real
   dependencies, applies the schema, and listens on `HOST:PORT`.
3. **Error handler**: maps `AppError` to `ErrorResponse` (including `retryable`
   and `retryAfterSeconds`, both taken from the `AppError`), unknown errors to
   `INTERNAL`, never leaks stack traces or causes.
4. **Logging**: pino with redaction of `req.headers.authorization`, `cookie`, and
   any `token` field.
5. **`GET /api/health`** with DB ping.
6. **`CollectionService`** with tests (cache hit, force, in-flight join,
   success, failures, `lastGood`).
7. **`POST /api/collections`**, request schema validation.
8. **`GET /api/posts`**.
9. **Startup**: `ensureSchema`, log the DB path and collector mode, then listen.
   Graceful shutdown closes the DB.
10. **Endpoint tests** with `app.inject()` using a fake collector and
    in-memory DB.
11. **Manual curl check** against the real collector once `02` is merged.
12. Tick the definition of done below.

## Entities

### Endpoints

#### `POST /api/collections`

Request body (`CollectRequest`): `{ term: string, force?: boolean }`.
Validated by zod: `term` string 1-200 chars before normalization.

| Case | Status | Body |
|---|---|---|
| Success, live | 200 | `CollectionResponse` with `source: "live"` |
| Success, from cache | 200 | `CollectionResponse` with `source: "cache"` |
| Success, zero posts | 200 | `CollectionResponse` with `posts: []`, `postCount: 0` |
| Invalid body or term | 400 | `ErrorResponse` `INVALID_TERM` |
| Subreddit not found/private | 404 | `NOT_FOUND_SUBREDDIT` |
| Rate limited | 429 | `RATE_LIMITED`, `retryAfterSeconds`, `Retry-After` header |
| Upstream/auth/contract failure | 502 or 504 | per error table in 00 |
| DB failure | 500 | `DB_ERROR` |

On any error after validation, the response includes `lastGood` (the previous
successful `CollectionResponse` for the term, `source: "cache"`) if one exists,
so the UI can keep showing data next to the error.

#### `GET /api/posts?term=...`

Reads the DB only, never calls Reddit. Normalizes the term; invalid term is 400.
Returns `CollectionResponse` for the latest successful run with
`source: "cache"`, or `{ collection: null, posts: [] }` when the term was never
collected (200, not 404, since "not collected yet" is a normal state).

#### `GET /api/health`

`{ status: "ok", db: "ok", collectorMode: "live" | "fixture", staleAfterSeconds: number }`.
If the DB ping fails: 503 with `db: "error"`. The UI reads `staleAfterSeconds`
and `collectorMode` from here so the two values have one source of truth.

### `CollectionService.collect(term, force)`

Algorithm, in order:

1. `subreddit = normalizeTerm(term)` (throws `INVALID_TERM`).
2. If `!force`: `fresh = repository.getFreshSuccess(subreddit, TTL)`.
   If found, return `{ collection: {...fresh, source: "cache"}, posts: getFeed }`.
3. If an in-flight promise exists for `subreddit`, await and return it.
   Otherwise create it (steps 4-6) and store it in `inflight: Map<string, Promise>`;
   remove the entry in `finally`.
4. `startedAt = clock.now()`. `posts = await collector.collect(subreddit, MAX_POSTS)`.
5. On success: `summary = repository.recordSuccess(subreddit, posts, startedAt)`.
6. On a collector or DB error: `repository.recordFailure(subreddit, code, startedAt)`
   then rethrow the `AppError`.
7. Respond using `getFeed(summary.id)`, so what the user sees is what was stored.

Notes:

- A `force` request still joins an in-flight request for the same term.
- Cache hits create no `collections` rows (they are not collection attempts).
- `lastGood` is attached in the route's error handler by calling
  `getLatestSuccess` (best effort; a failure there is swallowed and logged).
- The in-flight map is per process. That is correct for a single local server
  and is documented as a limitation.

### Fastify wiring

| Concern | Choice |
|---|---|
| Bind address | `127.0.0.1` only; no CORS (the dev proxy makes requests same-origin) |
| Body limit | 1 KB |
| Handler time | Bounded by the collector's `COLLECTION_DEADLINE_MS` (02). Fastify's `requestTimeout` only covers receiving the request, so it is left at its default and not relied on |
| Rate limiting of our own API | None (local tool); a note in limitations |
| Static serving | Optional: if `frontend/dist` exists, serve it at `/` so `npm run build && npm start` runs a single process. Dev uses Vite |
| Fixture mode | `COLLECTOR_MODE=fixture` swaps in the fixture collector and defaults `DB_PATH` to `data/fixture.db`; `/api/health` reports it. Collection responses carry no mode field; health is the single source |

### Dependencies injected into `buildApp`

| Dep | Real | Test |
|---|---|---|
| `repository` | SQLite file | `:memory:` |
| `collector` | `createCollector(config)` | stub returning fixtures or throwing chosen `AppError` |
| `clock` | `Date` | controllable |
| `config` | parsed env | literal object |

## Version control plan

- Branch: `feat/app`.
- Commits, in order:
  1. `feat(api): add buildApp with error handler and redacting logger`
  2. `feat(api): add health endpoint`
  3. `feat(api): add collection service with cache and in-flight guard`
  4. `feat(api): add POST /api/collections`
  5. `feat(api): add GET /api/posts`
  6. `feat(api): add startup schema setup and graceful shutdown`
  7. `feat(api): add fixture collector mode and optional static serving`
  8. `test(api): add endpoint tests for success, empty, cache and error paths`
- Done when: endpoint tests pass; `curl` flow works against the fake
  collector; with `02` done, `curl` returns real posts.

## Definition of done

- [ ] All rows in the endpoint tables above have a test.
- [ ] No response body or log line contains a token, header value, or stack trace.
- [ ] Two simultaneous POSTs for one term cause one collector call (test).
- [ ] Cache hit makes zero collector calls; `force` bypasses it (test).
- [ ] `GET /api/posts` never triggers a collector call (test).
- [ ] Server refuses to start with a clear message on invalid config.
- [ ] Fixture mode writes only to `data/fixture.db` (test).
