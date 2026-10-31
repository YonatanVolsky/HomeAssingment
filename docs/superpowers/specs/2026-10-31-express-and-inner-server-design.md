# Express web service and inner collector server

Date: 2026-10-31. Status: approved in conversation, awaiting review of this spec.
Builds on: `2026-10-31-term-protocols-design.md` (the term normalizer is reused as is).

## Goal

Split the backend in two:

- **Express** (Node) is the web service the browser talks to: a REST API over HTTP and JSON,
  and the static UI in a production-like run.
- **The inner server** (Python) does what the brief asks: a term comes in, the matching
  collection comes out as JSON. It speaks a small line-based JSON protocol over TCP sockets,
  serves connections from a thread pool, and runs the existing collector, service and database
  unchanged.

Every request is a CRUD command with arguments. Only GET exists. Which HTTP route becomes which
command, and which inner handler serves which resource, are presets chosen at startup from
configuration, like `TERM_PROTOCOL`.

## Decisions

| Question | Decision |
|---|---|
| Who faces the browser | Express on `127.0.0.1:3001` (the Vite proxy target is unchanged) |
| Inner server | Python on `127.0.0.1:3002`, localhost only, thread pool, chosen with `SERVER` (only `threadpool`) |
| Split of work | Express: REST routes, HTTP status and headers, static UI. Python: message validation, term normalization, command dispatch, handlers, collection. HTTP concepts never reach Python; domain rules never reach Node |
| What GET means | From the user's view: return the collection matching the term, from storage or collected live, according to `freshness` |
| GET arguments | `term`, and `freshness`: `auto` (default; stored if younger than the TTL, else live), `live` (always collect; Refresh), `stored` (never call Reddit; restore on reload) |
| Wire framing | One request per TCP connection, one UTF-8 JSON object per line (`\n`), reply the same way, then close |
| Old endpoints | `POST /api/collections` and `GET /api/posts?term=` are replaced; FastAPI and uvicorn are removed |
| Health | A resource like any other: `GET health` |

## Request path

```
browser ──HTTP──► Express :3001 ──TCP line──► ThreadPoolServer :3002
                  routes → command            ─► RequestNormalizer ─► Dispatcher ─► PostsHandler.get()
                  reply → HTTP status/JSON        (validate, term)     (resource)     HealthHandler.get()
                                                                                       │ on the event-loop thread
                                                                                       ▼
                                                                         CollectionService → collector / SQLite
```

## Wire protocol (written up in `docs/inner-protocol.md`)

Request, one line:

```json
{"v": 1, "command": "GET", "resource": "posts", "args": {"term": "r/ubisoft", "freshness": "auto"}}
{"v": 1, "command": "GET", "resource": "health"}
```

Reply, one line:

```json
{"ok": true, "result": {"collection": {...}, "posts": [...]}}
{"ok": false, "error": {"code": "RATE_LIMITED", "message": "...", "retryable": true, "retryAfterSeconds": 30}, "lastGood": {...}}
```

- `result` for posts is today's `CollectionResponse` JSON (camelCase), unchanged. For health
  it is `{"status": "ok"|"error", "db": "ok"|"error", "collectorMode": ..., "staleAfterSeconds": ...}`.
- `lastGood` appears only when a collection failed and an earlier successful feed exists.
- A request line longer than 4096 bytes, bytes that are not UTF-8 JSON, `v` other than 1, an
  unknown command or resource, a command the resource does not support, or bad arguments all
  get an error reply with code `INVALID_REQUEST` ("The request is not valid.", not retryable).
  An invalid term gets `INVALID_TERM` as today. A term longer than 200 characters before
  normalizing is `INVALID_TERM`.
- The server waits at most 5 seconds for the request line, then closes the connection without
  a reply.
- The inner server never deals with HTTP status codes. The error table in `app/errors.py` keeps
  auto-retry, UI retryability and messages; its HTTP status column moves to Express.

## Inner server (Python)

### `backend/app/inner/`

- **`server.py`**: `InnerServer` interface (`serve_forever()`, `shutdown()`, `address`);
  `ThreadPoolServer(host, port, threads, chain, logger)`. Accepts connections, hands each to a
  `ThreadPoolExecutor(max_workers=threads)`, reads one line within the limits above, calls
  `chain.handle(line_bytes) -> bytes`, writes the reply line, closes. It never raises into
  the accept loop: an unexpected error writes an `INTERNAL` reply and is logged.
- **`loop_thread.py`**: `LoopThread`, one asyncio event loop on a daemon thread, with
  `run(coro, timeout)` and `call(fn, timeout)` for worker threads, and `stop()`. Every service,
  repository and collector call runs on this thread, so the existing async code (token cache,
  shared in-flight runs) is unchanged and SQLite is used from one thread only.
- **`protocol.py`**: `encode_reply(...)` and the parsing of a request line into
  `RawRequest(v, command, resource, args)`; the only module that knows the wire format.
- **`normalizer.py`**: `RequestNormalizer(term_normalizer, next)`. Parses and validates the
  message, uppercases `command`, normalizes `args.term` with the injected term normalizer
  (and applies the 200-character guard before it), and calls
  `next.handle(Command(verb, resource, args))`.
- **`dispatcher.py`**: `Command(verb, resource, args)` (frozen); `Dispatcher(handlers)` maps
  resource name → handler and calls `handler.handle(command)`. Unknown resource →
  `INVALID_REQUEST`.
- **`handlers.py`**: `ResourceHandler` base with `handle(command)` dispatching to `get`, `post`,
  `put`, `delete`; each defaults to raising `INVALID_REQUEST` ("not supported"), so a resource
  overrides only the verbs it supports.
  - `PostsHandler(service, loop)`: `get(args)` reads `freshness` (default `auto`; other values
    → `INVALID_REQUEST`) and runs on the loop: `auto` → `service.collect(term, force=False)`,
    `live` → `service.collect(term, force=True)`, `stored` → `service.get_posts(term)`.
    On a failed collection it raises the error with the last good feed attached
    (`CollectionFailed(AppError)` carrying `last_good`), which the protocol layer writes as
    `lastGood`.
  - `HealthHandler(repository, config, loop)`: the health result above.
- **Presets**: `INNER_ROUTES` selects a resource → handler table (only `collector`:
  `posts` → `PostsHandler`, `health` → `HealthHandler`); `SERVER` selects the server
  implementation (only `threadpool`). Both are read-only tables; unknown names fail
  `load_config`.

### Composition: `backend/app/composition.py`

`build_inner(config) -> InnerApp` builds everything from `Config` (`InnerApp` holds the server
and a `close()` that shuts the rest down): term normalizer (moved here from `collector/factory.py`),
repository, collector, service, `LoopThread`, handlers, dispatcher, request normalizer, server.
At startup every route in the `INNER_ROUTES` preset must name a handler that exists, otherwise
`ConfigError`. `main.py` builds it, logs the address, serves, and on SIGINT/SIGTERM shuts down
in order: server (stop accepting, finish running requests), worker pool, loop, database.

### Configuration changes (Python)

| Variable | Default | Notes |
|---|---|---|
| `INNER_HOST` / `INNER_PORT` | `127.0.0.1` / `3002` | Replace Python's `HOST`/`PORT`. Port 0 still allowed (tests) |
| `SERVER` | `threadpool` | Inner server implementation |
| `SERVER_THREADS` | `8` | 1-64 |
| `INNER_ROUTES` | `collector` | Resource → handler preset |

Everything else (`COLLECTOR_MODE`, `DB_PATH`, `TERM_PROTOCOL`, limits, `LOG_LEVEL`) is unchanged.
`fastapi` and `uvicorn` leave `requirements.txt`; `pydantic` is added explicitly.
`backend/app/api.py` is deleted.

## Express web service: `server/` (new npm workspace)

Plain JavaScript (ESM), Express 5, Node 22+.

- **`config.js`**: reads and validates `PORT` (3001), `HOST` (127.0.0.1), `INNER_HOST`
  (127.0.0.1), `INNER_PORT` (3002), `API_ROUTES` (`rest`), `INNER_TIMEOUT_MS` (30000, above
  the inner 25 s collection deadline). Invalid values stop startup with a message naming the
  variable.
- **`routes.js`**: route presets. `rest`:
  `GET /api/posts` → `{command: 'GET', resource: 'posts', args: {term, freshness}}` from the
  query string (absent values omitted, so Python applies defaults);
  `GET /api/health` → `{command: 'GET', resource: 'health'}`.
- **`innerClient.js`**: `send(message) -> reply`. Opens a socket, writes one line, reads one
  line, enforces `INNER_TIMEOUT_MS`. Connection refused or reset → an `INNER_UNAVAILABLE`
  error; timeout → `UPSTREAM_TIMEOUT`; an unreadable reply → `INTERNAL`.
- **`errors.js`**: the HTTP status table, moved from Python's error table:
  `INVALID_TERM` 400, `INVALID_REQUEST` 400, `NOT_FOUND_SUBREDDIT` 404, `RATE_LIMITED` 429,
  `DB_ERROR` 500, `INTERNAL` 500, `UPSTREAM_AUTH` 502, `UPSTREAM_ERROR` 502, `CONTRACT_ERROR` 502,
  `INNER_UNAVAILABLE` 503 ("The collector service is not running.", retryable),
  `UPSTREAM_TIMEOUT` 504, `NOT_FOUND` 404 (unknown `/api` path). Unknown codes → 500.
- **`app.js`**: `createApp({routes, inner, staticDir})`. Mounts each route; a reply with
  `ok: true` → 200 with `result` as the body; `ok: false` → the mapped status with
  `{error, lastGood?}` and `Retry-After` when `retryAfterSeconds` is set. API responses carry
  `Cache-Control: no-store`. Unknown `/api/*` → 404 `NOT_FOUND`. When `staticDir` holds
  `index.html`, other paths serve files from it with the `index.html` fallback, never outside it.
  `GET /api/health` with the inner server down → 503 `INNER_UNAVAILABLE`.
- **`index.js`**: builds the app from config and listens.

## Frontend

- `api/client.js`: `getFeed(term, freshness, options)` replaces `collect` and `getPosts`
  (`GET /api/posts?term=…&freshness=…`). `getHealth` is unchanged.
- Search uses `auto`, Refresh `live`, restore on reload `stored`. The reducer, hook and
  components are otherwise unchanged; `INNER_UNAVAILABLE` is shown like any other error.

## Scripts and run

- `npm run dev` starts three processes (inner, server, frontend); `npm start` starts the inner
  server and Express (which serves `frontend/dist`). `npm test` runs backend, server and
  frontend tests; `npm run lint` covers the new workspace.
- `scripts/smoke.sh` targets Express (`BASE_URL` default `http://127.0.0.1:3001`) and the new
  URLs.

## Error handling summary

The inner server turns every failure into an error reply and never drops a well-formed
request without one (except the read timeout). Express turns every reply into an HTTP
response and turns transport failures into `INNER_UNAVAILABLE` or `UPSTREAM_TIMEOUT`. The
browser sees the same error body shape as today, plus the new code.

## Testing (written before the code)

- **Inner, per stage with fakes**: protocol parsing (each invalid case above), the request
  normalizer (term normalized, 200-character guard, verb uppercased), dispatcher (unknown
  resource), `ResourceHandler` (unsupported verbs), `PostsHandler` (each freshness, invalid
  freshness, `lastGood` attached on failure), `HealthHandler`, `LoopThread` (result, exception,
  timeout).
- **Inner, real socket on port 0**: a round trip; an oversize line; a client that sends nothing
  (closed after the timeout); malformed JSON; more concurrent connections than worker threads
  all answered; two concurrent `auto` requests for one term share one collection; the existing
  service behaviours from `test_api.py` (cache, `lastGood`, rate limit with
  `retryAfterSeconds`) over the protocol; fixture mode end to end through `build_inner`.
- **Config**: the new variables accepted and rejected.
- **Express (Vitest + supertest)**: each route builds the right message (fake inner client);
  status mapping for each code; `Retry-After`; `no-store`; unknown `/api` path 404; health when
  the inner server is down; static files and the path-escape guard; config validation; and
  `innerClient` against a fake TCP server (round trip, refused, timeout, garbage reply).
- **Frontend**: client and hook tests for `getFeed` and the three freshness uses.
- **End to end**: `scripts/smoke.sh` against Express with the inner server in fixture mode.

## Delivery

Two plans, each leaving the app working:

1. **Inner server**: everything under "Inner server (Python)", built next to the current
   FastAPI server, which keeps running and serving the UI until plan 2. `npm run dev` gains the
   inner server as a third process temporarily. Python keeps `HOST`/`PORT` for FastAPI until
   plan 2 removes them; `INNER_HOST`/`INNER_PORT` are added in plan 1.
2. **Express**: the `server/` workspace, the frontend switch to `getFeed`, removal of FastAPI,
   `api.py` and the old endpoints, the scripts, and the documentation (README run steps and
   configuration, API section, `docs/inner-protocol.md`, DESIGN.md: request path, why two
   servers, the GET-that-writes trade-off, `/api/docs` gone; HANDOFF.md).

## Known limitations

- `GET /api/posts` with `freshness=auto` or `live` can collect and write; it is not a "safe"
  method in HTTP's sense. Chosen from the user's view; `no-store` keeps caches and prefetchers
  from repeating it.
- One connection per request costs a TCP handshake each time; fine on localhost.
- All database and Reddit work runs on one event-loop thread; the worker pool adds concurrency
  for connection handling and waiting, not for database writes. Fine for one local user.
- The switch from term-protocols' known limitation still applies (separate `DB_PATH` per
  protocol).

## Out of scope

- Commands other than GET; other inner server implementations; persistent connections.
- Authentication between Express and the inner server (both bind to localhost).
- Docker files (the presets are ready for environment-based selection).
