# Express Web Service Implementation Plan (plan 2 of 2)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Put an Express web service on :3001 in front of the inner server, switch the frontend to `GET /api/posts?term&freshness`, and remove FastAPI.

**Architecture:**
- A new npm workspace, `server/` (plain JS, ESM, Express 5). It maps REST routes, chosen from the `API_ROUTES` preset, to one-line commands sent over TCP to the inner server (`innerClient`), and maps replies to HTTP status and JSON (`errors.js`). It also serves `frontend/dist`.
- The frontend's API client gets a single `getFeed(term, freshness)`.
- Python loses `api.py`, `main.py` and `python -m app`. `python -m app.inner` is the only backend entry point.

**Tech Stack:** Node 22+, Express ^5.1.0, Vitest ^5.0.5, supertest ^7.1.0; Python 3.11+ (removals only).

**Spec:** `docs/superpowers/specs/2026-10-31-express-and-inner-server-design.md` (this plan covers "Delivery" item 2). The inner server from plan 1 is merged; its wire protocol is in `backend/app/inner/protocol.py`.

## Global Constraints

- Express listens on `HOST=127.0.0.1`, `PORT=3001` (the Vite proxy target is unchanged). The inner server is at `INNER_HOST=127.0.0.1`, `INNER_PORT=3002`. `API_ROUTES` defaults to `rest`.
- **Deviation from the spec (ruled in this plan):** `INNER_TIMEOUT_MS` defaults to **35000**, not 30000, and the frontend's `CLIENT_TIMEOUT_MS` goes from 35000 to **40000**. The inner worker timeout is 25 s + 5 s = 30 s, and each layer must wait longer than the one below it, so the inner reply (with `lastGood`) arrives before Express gives up. Raised in the plan 1 review.
- Routes (`rest`):
  - `GET /api/posts` → `{"v":1,"command":"GET","resource":"posts","args":{term, freshness}}`. A query value is included only when present, even if empty; absent values are omitted.
  - `GET /api/health` → `{"v":1,"command":"GET","resource":"health"}`.
- HTTP status table (`server/src/errors.js`):

  | Status | Codes |
  |---|---|
  | 400 | `INVALID_TERM`, `INVALID_REQUEST` |
  | 404 | `NOT_FOUND_SUBREDDIT`, `NOT_FOUND` |
  | 429 | `RATE_LIMITED` |
  | 500 | `DB_ERROR`, `INTERNAL`, and any unknown code |
  | 502 | `UPSTREAM_AUTH`, `UPSTREAM_ERROR`, `CONTRACT_ERROR` |
  | 503 | `INNER_UNAVAILABLE` |
  | 504 | `UPSTREAM_TIMEOUT` |

- Express's own error bodies, with the same `{code, message, retryable}` shape the inner server uses:
  - `INNER_UNAVAILABLE`: "The collector service is not running.", retryable;
  - `UPSTREAM_TIMEOUT`: "Reddit took too long to respond.", retryable;
  - `INTERNAL`: "Something went wrong.", retryable;
  - `NOT_FOUND`: "Not found.", not retryable.
- API responses carry `Cache-Control: no-store`. A `retryAfterSeconds` in the error becomes a `Retry-After` header.
- The response JSON seen by the browser is unchanged: `{collection, posts}` on success, `{error, lastGood?}` on failure.
- Test first; Conventional Commits ending with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`. Lint must pass before every commit. Before the last commit: `npm test`, `npm run lint`, `scripts/check-secrets.sh`, `scripts/check-compliance.sh`, and `scripts/smoke.sh` against a running stack, all green.

## Review Focus

1. **The inner server dies or restarts mid-request** (connection reset after connecting): `INNER_UNAVAILABLE` 503, never an unhandled rejection that crashes Express. Test in Task 2.
2. **A reply split across many TCP packets, or bytes arriving after the newline**: the client assembles exactly the first line and parses it. Test in Task 2.
3. **A term with characters that need URL encoding** (`r/ubisoft?x=1&freshness=live`, `é`, spaces): it reaches the inner server unchanged as the `term` argument, and `freshness` cannot be injected through it. Tests in Tasks 3 and 5.
4. **Repeated query parameters** (`?term=a&term=b`): Express takes the first value and sends a string, never an array. Test in Task 3.
5. **Static path escape** (`/..%2f..%2fpackage.json`, `/%2e%2e/backend/app/config.py`): it never serves a file outside `frontend/dist`. Test in Task 3.

---

### Task 1: The `server/` workspace, `config.js` and `errors.js`

**Files:**
- Create: `server/package.json` (name `@reddit-collector/server`, `"type": "module"`, scripts `dev: node --watch src/index.js`, `start: node src/index.js`, `test: vitest run`; dependency `express@^5.1.0`; dev dependencies `vitest@^5.0.5`, `supertest@^7.1.0`), `server/src/config.js`, `server/src/errors.js`
- Test: `server/src/config.test.js`, `server/src/errors.test.js`
- Modify:
  - root `package.json`: add `"server"` to `workspaces`;
  - `eslint.config.js`: a block for `server/**/*.js` with `globals.node`, plus `globals.vitest` for `server/**/*.test.js`.

**Interfaces:**
- Produces, in `config.js`:
  - `class ConfigError extends Error`
  - `loadConfig(env) -> {port, host, innerHost, innerPort, apiRoutes, innerTimeoutMs}`. Empty strings count as unset.
  - Ranges: `PORT` and `INNER_PORT` are 0–65535 integers, `HOST` and `INNER_HOST` non-empty, `INNER_TIMEOUT_MS` an integer 1000–120000, `API_ROUTES` a key of `ROUTE_PRESETS` (Task 3; until then, validate against `['rest']` imported from a constant `ROUTE_NAMES` in `routes.js`, created as a stub exporting `ROUTE_NAMES = ['rest']`).
  - The error message format is `Invalid configuration: <VAR>: <reason>`.
- Produces, in `errors.js`:
  - `statusFor(code) -> number`, following the table above;
  - `errorBody(code) -> {code, message, retryable}` for Express's own codes (`INNER_UNAVAILABLE`, `UPSTREAM_TIMEOUT`, `INTERNAL`, `NOT_FOUND`);
  - `class InnerError extends Error`, which has a `code`.

- [ ] **Step 1: Write the failing tests**
  - `config.test.js`:
    - defaults (`port 3001`, `host '127.0.0.1'`, `innerHost '127.0.0.1'`, `innerPort 3002`, `apiRoutes 'rest'`, `innerTimeoutMs 35000`);
    - numeric strings are parsed;
    - empty strings mean defaults;
    - `PORT=0` is accepted;
    - each rejection throws `ConfigError` matching `/Invalid configuration: VAR/`: `PORT=70000`, `PORT=abc`, `INNER_PORT=-1`, `INNER_TIMEOUT_MS=999`, `API_ROUTES=nope`, `HOST=` set to spaces only.
  - `errors.test.js`:
    - `statusFor` for every code in the table;
    - `statusFor('SOMETHING_NEW') === 500`;
    - `errorBody('INNER_UNAVAILABLE')` deep-equals `{code: 'INNER_UNAVAILABLE', message: 'The collector service is not running.', retryable: true}`, and likewise for the other three codes.
- [ ] **Step 2: Run, and confirm the failure**
  - Run: `npm install && npm test -w server`
  - Expected: Vitest fails to resolve `./config.js` and `./errors.js`.
- [ ] **Step 3: Implement** `config.js`, `errors.js`, and the `routes.js` stub.
- [ ] **Step 4: Run, and confirm everything passes**
  - Run: `npm test -w server && npm run lint`
  - Expected: all pass, and lint is clean.
- [ ] **Step 5: Commit** with `feat(server): add the Express workspace with config and the HTTP status table`.

### Task 2: `innerClient.js`

**Files:**
- Create: `server/src/innerClient.js`
- Test: `server/src/innerClient.test.js`, using a fake TCP server built with `net.createServer` on port 0.

**Interfaces:**
- Consumes: `InnerError` (Task 1).
- Produces: `createInnerClient({host, port, timeoutMs}) -> {send(message) -> Promise<reply>}`.
  - `send` opens a connection, writes `JSON.stringify(message) + '\n'`, collects data until the first `\n`, then destroys the socket and resolves with `JSON.parse` of that line.
  - It rejects with `InnerError`:
    - code `INNER_UNAVAILABLE` on `ECONNREFUSED`, `ECONNRESET`, `EPIPE`, or the connection closing before a newline;
    - `UPSTREAM_TIMEOUT` when there's no full line within `timeoutMs`;
    - `INTERNAL` when the line isn't JSON, or is not an object with a boolean `ok`, or more than 1 MB arrives without a newline.
  - Exactly one settlement per call. The socket is always destroyed.

- [ ] **Step 1: Write the failing tests**
  - `sends one line and resolves with the reply`: the fake server records the received line (asserted equal to the JSON + `\n`) and answers `{"ok":true,"result":{"a":1}}\n`.
  - `assembles a reply split across packets and ignores bytes after the newline`: the server writes the reply in 3 chunks 20 ms apart, then `garbage`.
  - `reports INNER_UNAVAILABLE when nothing listens`: a port from a server that has been closed.
  - `reports INNER_UNAVAILABLE when the server closes or resets before replying` (Review Focus 1): (a) the server calls `socket.end()` without a newline; (b) it calls `socket.destroy()` right after reading.
  - `reports UPSTREAM_TIMEOUT when no reply arrives in time`: `timeoutMs: 100`, and the server never answers. The test completes in under 1 s.
  - `reports INTERNAL for a reply that is not a protocol object`: `not json\n`, `[]\n` and `{"result":1}\n`.
- [ ] **Step 2: Run, and confirm the failure**
  - Run: `npm test -w server`
  - Expected: `innerClient.js` can't be resolved.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run, and confirm everything passes**
  - Run: `npm test -w server && npm run lint`
  - Expected: all pass.
- [ ] **Step 5: Commit** with `feat(server): add the TCP client for the inner server`.

### Task 3: `routes.js` and `app.js`

**Files:**
- Modify: `server/src/routes.js` (replace the stub)
- Create: `server/src/app.js`
- Test: `server/src/routes.test.js`, `server/src/app.test.js` (supertest, with a fake `inner` object `{send: vi.fn()}`)

**Interfaces:**
- Consumes: `statusFor`, `errorBody` and `InnerError` (Task 1); the shape of `innerClient` (Task 2).
- Produces:
  - in `routes.js`:
    - `ROUTE_PRESETS`, frozen: `{rest: [{method: 'get', path: '/api/posts', toMessage(query)}, {method: 'get', path: '/api/health', toMessage()}]}`;
    - `ROUTE_NAMES = Object.keys(ROUTE_PRESETS)`;
    - `firstValue(v)` returns the first element of an array, otherwise the value.
  - in `app.js`: `createApp({routes, inner, staticDir}) -> express app`.
    - Each route awaits `inner.send(route.toMessage(req.query))`.
    - `ok: true` → 200 with the body `reply.result`.
    - `ok: false` → `statusFor(reply.error.code)` with the body `{error: reply.error, lastGood?}` and `Retry-After` when `reply.error.retryAfterSeconds` is a number.
    - An `InnerError` → `statusFor(code)` with `{error: errorBody(code)}`. Any other thrown error → 500 `INTERNAL`.
    - `/api/*` responses set `Cache-Control: no-store`. An unknown `/api/*` path gets 404 with `{error: errorBody('NOT_FOUND')}`.
    - When `staticDir` contains `index.html`, it serves static files from it, and any other GET outside `/api` gets `index.html`.

- [ ] **Step 1: Write the failing tests**
  - `routes.test.js`:
    - `posts builds the GET posts command`: `toMessage({term: 'r/x', freshness: 'live'})` deep-equals `{v: 1, command: 'GET', resource: 'posts', args: {term: 'r/x', freshness: 'live'}}`.
    - `omits absent values`: `toMessage({})` has `args` equal to `{}`; `toMessage({term: ''})` has `args.term === ''`.
    - `takes the first of repeated values` (Review Focus 4): `{term: ['a', 'b']}` gives `args.term === 'a'`.
    - `health builds the health command`.
  - `app.test.js`:
    - `GET /api/posts sends the command and returns the result`: assert `inner.send` was called with the posts message, the status is 200, the body is the result, and `cache-control` is `no-store`.
    - `an encoded term reaches the inner server unchanged` (Review Focus 3): the query string `term=r%2Fubisoft%3Fx%3D1%26freshness%3Dlive&freshness=auto` gives a message with `args` equal to `{term: 'r/ubisoft?x=1&freshness=live', freshness: 'auto'}`.
    - `error replies map to status, body and Retry-After`:
      - `{ok: false, error: {code: 'RATE_LIMITED', message: 'm', retryable: true, retryAfterSeconds: 30}, lastGood: {x: 1}}` → 429, body `{error: ..., lastGood: {x: 1}}`, `retry-after: 30`;
      - `NOT_FOUND_SUBREDDIT` → 404;
      - `INVALID_TERM` → 400.
    - `inner transport errors map to Express error bodies`: `send` rejects with `new InnerError('INNER_UNAVAILABLE')` → 503 with `errorBody('INNER_UNAVAILABLE')`; with `UPSTREAM_TIMEOUT` → 504.
    - `an unexpected exception is a safe 500`: `send` rejects with `new Error('secret')` → 500 `INTERNAL`, and the body doesn't contain `secret`.
    - `GET /api/health with the inner server down is 503`.
    - `unknown API paths are JSON 404s`: `GET /api/nope` and `POST /api/posts`.
    - Static, using a temp dir with `index.html` (content `<title>UI</title>`) and `app.js`:
      - `/` and `/some/page` → the index;
      - `/app.js` → the file;
      - `/..%2f..%2fpackage.json` and `/%2e%2e/%2e%2e/package.json` → never the repo's `package.json` (assert the body doesn't contain `"workspaces"`) (Review Focus 5);
      - with no `staticDir`, `/` → 404.
- [ ] **Step 2: Run, and confirm the failure**
  - Run: `npm test -w server`
  - Expected: failures for the missing `ROUTE_PRESETS` and `app.js`.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run, and confirm everything passes**
  - Run: `npm test -w server && npm run lint`
  - Expected: all pass.
- [ ] **Step 5: Commit** with `feat(server): add the REST routes and the Express app`.

### Task 4: `index.js`, the run scripts, and the smoke test

**Files:**
- Create: `server/src/index.js`
- Modify:
  - root `package.json` scripts:
    - `dev`: `concurrently -n inner,server,frontend -c magenta,blue,green "npm:dev:inner" "npm:dev:server" "npm:dev:frontend"`;
    - add `dev:server` (`npm run dev -w server`);
    - remove `dev:backend`;
    - `start`: `concurrently -n inner,server "npm:start:inner" "npm:start:server"`;
    - add `start:inner` (`cd backend && .venv/bin/python -m app.inner`) and `start:server` (`npm start -w server`);
    - `test`: `npm run test:backend && npm run test:server && npm run test:frontend`;
    - add `test:server` (`npm test -w server`).
  - `scripts/smoke.sh`: use `GET /api/health`, `GET /api/posts?term=` (expect 400 `INVALID_TERM`), `GET /api/posts?term=$SMOKE_TERM&freshness=live` (≥1 post, source `live`), then `freshness=auto` (source `cache`), then `freshness=stored` (the same posts).
- Test: `server/src/index.test.js` (a subprocess)

**Interfaces:**
- Consumes: `loadConfig` and `ConfigError`, `createInnerClient`, `ROUTE_PRESETS`, `createApp`.
- Produces: `node server/src/index.js`. It serves on `host:port` with `staticDir = <repo>/frontend/dist` and logs `web service listening on http://host:port (inner server host:innerPort)`. On a `ConfigError` it prints the message to stderr and exits 1.

- [ ] **Step 1: Write the failing test** `index.test.js`:
  - `starts and answers health as 503 when the inner server is down`: spawn `node src/index.js` with `PORT` set to a free port and `INNER_PORT` to a closed port; poll `GET /api/health` until it answers; expect 503 `INNER_UNAVAILABLE`; kill the child.
  - `refuses invalid configuration`: `PORT=abc` → exit code 1, and stderr contains `Invalid configuration: PORT`.
- [ ] **Step 2: Run, and confirm the failure**
  - Run: `npm test -w server`
  - Expected: the child fails because `index.js` is missing.
- [ ] **Step 3: Implement** `index.js`, the scripts, and `smoke.sh`.
- [ ] **Step 4: Verify end to end**
  - Run: `npm test -w server && npm run lint`. Expected: pass.
  - Then start `COLLECTOR_MODE=fixture DB_PATH=<tmp>/smoke.db npm start` in the background and run `scripts/smoke.sh`.
  - Expected: every check PASS, 0 failed. Stop the stack.
- [ ] **Step 5: Commit** with `feat(server): run the web service with the inner server; smoke test the stack`.

### Task 5: Frontend switch to `getFeed`

**Files:**
- Modify:
  - `frontend/src/api/client.js`: replace `collect` and `getPosts` with `getFeed(term, freshness, options)`; `CLIENT_TIMEOUT_MS = 40_000`, with its comment updated to "above Express's 35 s inner timeout".
  - `frontend/src/state/useCollection.js`: the dependency becomes `api = { getFeed }`; `run(term, force)` calls `api.getFeed(term, force ? 'live' : 'auto', {signal})`; `retry` uses `'auto'`.
  - `frontend/src/App.jsx`: restore calls `getFeed(initialTerm, 'stored', {signal})`.
  - `frontend/src/api/types.js` (the doc comment for the API shapes).
- Test: `frontend/src/api/client.test.js`, `frontend/src/state/useCollection.test.js`, `frontend/src/App.test.jsx` (the fetch mock routes on `/api/posts` and reads `freshness` from the URL; the `/api/collections` branch is removed)

**Interfaces:**
- Produces: `getFeed(term: string, freshness: 'auto'|'live'|'stored', options) -> Promise<CollectionResponse>`, sending `GET /api/posts?term=<encodeURIComponent(term)>&freshness=<freshness>`.

- [ ] **Step 1: Update the tests first**
  - `client.test.js`:
    - `getFeed GETs the term and freshness in the query string`: `getFeed('r/ubi soft?&x', 'live', {fetchImpl})` calls `/api/posts?term=r%2Fubi%20soft%3F%26x&freshness=live` with no body and no `method: 'POST'` (Review Focus 3);
    - the existing `collect` cases for errors, NETWORK, timeout and abort, moved to `getFeed`;
    - the `getPosts` case removed.
  - `useCollection.test.js`: rename the `collect` fakes to `getFeed`; the retry assertion becomes `toHaveBeenLastCalledWith('ubisoft', 'auto', expect.anything())`.
  - `App.test.jsx`:
    - `refreshes the shown subreddit with force` asserts the last posts URL contains `freshness=live`;
    - a search asserts `freshness=auto`;
    - restore on reload asserts `freshness=stored`.
- [ ] **Step 2: Run, and confirm the failure**
  - Run: `npm test -w frontend`
  - Expected: failures on the missing `getFeed`.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run, and confirm everything passes**
  - Run: `npm test -w frontend && npm run lint`
  - Expected: all 88+ tests pass.
- [ ] **Step 5: Commit** with `feat(ui): read feeds with GET /api/posts and a freshness argument`.

### Task 6: Remove FastAPI from the backend

**Files:**
- Delete:
  - `backend/app/api.py`, `backend/app/main.py`, `backend/app/__main__.py`;
  - `backend/tests/test_api.py`, `backend/tests/test_main.py`.
  - Also delete `LIVE_COLLECTION_AVAILABLE` from `mobile_api.py`, since only `main.py` used it.
- Modify:
  - `backend/app/config.py`: remove `PORT`, `HOST`, `Config.port` and `Config.host`.
  - `backend/app/errors.py`: remove `ErrorPolicy.http_status` and the `http_status` property; status lives in Express now.
  - `backend/requirements.txt`: remove `fastapi` and `uvicorn`; add `pydantic==<the version pip reports as installed>`.
  - `backend/tests/test_config.py` and `backend/tests/test_errors.py`: drop the port, host and status assertions.
- Test: move the behaviors from `test_main.py` that are still meaningful into `backend/tests/inner/test_inner_end_to_end.py`:
  - `test_the_feed_survives_a_restart_on_the_same_file`: collect, `close()`, build again on the same `DB_PATH`, and `stored` returns the same posts;
  - `test_re_collecting_never_duplicates_posts`: two `live` collections, then `SELECT COUNT(*) FROM posts` is 7;
  - `test_relative_db_paths_resolve_from_the_repo_root`, through `build_inner`.

- [ ] **Step 1: Write the moved tests in `test_inner_end_to_end.py`, and run them**
  - Run: `cd backend && .venv/bin/pytest tests/inner/test_inner_end_to_end.py -q`
  - Expected: they pass already. These are migrated behaviors, not new ones, and their FastAPI originals are about to be deleted. Record this in the ledger as a ruling.
- [ ] **Step 2: Change the config and error tests to the new shape** (no `port`/`host`; `test_error_table` without the status column). Run `cd backend && .venv/bin/pytest tests/test_config.py tests/test_errors.py -q`. Expected: they fail on the fields that still exist.
- [ ] **Step 3: Delete and modify as listed.** Reinstall: `backend/.venv/bin/pip uninstall -y fastapi uvicorn starlette && backend/.venv/bin/pip install -r backend/requirements-dev.txt`.
- [ ] **Step 4: Run the full suite and checks**, from the repo root:

  ```bash
  npm test
  npm run lint
  scripts/check-secrets.sh
  scripts/check-compliance.sh
  grep -rn "fastapi\|uvicorn" backend/app backend/tests backend/requirements*.txt package.json
  ```

  Expected: every test passes, lint is clean, both checks print OK, and the grep finds nothing.
- [ ] **Step 5: Commit** with `refactor(backend): remove FastAPI; the inner server is the only backend entry point`.

### Task 7: Documentation

**Files:**
- Create: `docs/inner-protocol.md`, covering framing, the request and reply shapes, limits, the error codes, and an `nc` example.
- Modify:
  - `README.md`: requirements, setup (`npm install` now also installs `server/`), run steps, the processes and ports table (Vite 5173, Express 3001, inner 3002), the configuration tables for Express and the inner server, an API section (`GET /api/posts?term&freshness`, `GET /api/health`), project layout, troubleshooting (`INNER_UNAVAILABLE`);
  - `.env.example`: `INNER_HOST`, `INNER_PORT`, `SERVER`, `SERVER_THREADS`, `INNER_ROUTES`, `API_ROUTES`, `INNER_TIMEOUT_MS`;
  - `DESIGN.md`: the request path, why two servers, the GET-that-writes trade-off, the timeout layering (30 s inner → 35 s Express → 40 s browser), `/api/docs` gone, and an updated known-limitations list;
  - `docs/HANDOFF.md`: the new architecture and how to run it.
- [ ] **Step 1: Write the docs.** Every command in the README must be one you ran in Task 4 or Task 6.
- [ ] **Step 2: Check.** Run `scripts/check-secrets.sh`; expected: OK. Then follow the README's Setup and Run steps exactly in a fresh shell, in fixture mode, and open `http://localhost:5173`: a search for `ubisoft` shows 7 cards.
- [ ] **Step 3: Commit** with `docs: document the Express web service, the inner protocol and the new run steps`.
