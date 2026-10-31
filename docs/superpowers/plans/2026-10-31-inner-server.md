# Inner Server Implementation Plan (plan 1 of 2)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a Python inner server that answers one-line JSON commands over TCP (term in, collection out), served by a thread pool, next to the existing FastAPI server, which keeps working unchanged.

**Architecture:**
- `ThreadPoolServer` reads one request line per connection and passes the bytes to `RequestNormalizer`.
- `RequestNormalizer` parses the line with `protocol.py`, normalizes the term, and calls `Dispatcher`. The dispatcher calls a `ResourceHandler` (`PostsHandler`, `HealthHandler`).
- Handlers run the existing `CollectionService` and repository on one asyncio event loop thread (`LoopThread`).
- `app/composition.py` builds everything from config, and `python -m app.inner` runs it.

**Tech Stack:** Python 3.11+ standard library (`socketserver`, `concurrent.futures`, `asyncio`, `json`), pydantic v2 config, pytest + anyio. Run from `backend/`.

**Spec:** `docs/superpowers/specs/2026-10-31-express-and-inner-server-design.md` (this plan covers "Delivery" item 1).

## Global Constraints

- Wire format: one UTF-8 JSON object per line (`\n`), one request per connection; reply one line, then close.
- Request: `{"v": 1, "command": "GET", "resource": "posts", "args": {"term": ..., "freshness": ...}}`, or `{"v": 1, "command": "GET", "resource": "health"}`.
- Success reply: `{"ok": true, "result": ...}`.
- Error reply: `{"ok": false, "error": {"code", "message", "retryable", "retryAfterSeconds"?}, "lastGood"?: ...}`. The error object is exactly `to_error_body(error)`.
- Request line limit: 4096 bytes. Read timeout: 5 seconds, after which the connection is closed with no reply.
- `INVALID_REQUEST`: "The request is not valid.", not retryable, no auto-retry.
- Term guard: more than 200 characters before normalizing is `INVALID_TERM`.
- `freshness`:
  - `auto` (the default) → `service.collect(term, force=False)`;
  - `live` → `service.collect(term, force=True)`;
  - `stored` → `service.get_posts(term)`.
- Defaults: `INNER_HOST=127.0.0.1`, `INNER_PORT=3002` (0 allowed), `SERVER=threadpool`, `SERVER_THREADS=8` (1–64), `INNER_ROUTES=collector`. Unknown preset names fail `load_config`.
- FastAPI (`python -m app`, `HOST`/`PORT`, `api.py`) stays exactly as it is in this plan.
- Test first; Conventional Commits ending with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`. Before the last commit: `npm test`, `npm run lint`, `scripts/check-secrets.sh` and `scripts/check-compliance.sh` are all green.

## Review Focus

1. **Non-object JSON or wrongly typed fields** must get an `INVALID_REQUEST` reply, not `INTERNAL`. Examples: `[]`, `null`, `"x"`, `args` not an object, `term` a number, `v` as `"1"`. Test in Task 1.
2. **A client that sends part of a line and then closes**, so the server reaches end of input with no `\n`, must get no reply and no logged traceback, and its worker must be freed for the next connection. Test in Task 6.
3. **A multi-byte character split across two TCP writes** (for example `é` in the term) must be reassembled. The term is then rejected as `INVALID_TERM` by the name rule, not as a decoding error. Test in Task 6.
4. **A collection that hangs** must not hold a worker forever. `LoopThread.run(coro, timeout)` raises `AppError('UPSTREAM_TIMEOUT')` on timeout. Handlers pass `config.collection_deadline_ms / 1000 + 5`. Tests in Tasks 2 and 5.
5. **More concurrent connections than worker threads** must queue and all be answered once the work completes, never refused. Test in Task 6.

---

### Task 1: Wire protocol and the `INVALID_REQUEST` code

**Files:**
- Modify: `backend/app/errors.py`: add `'INVALID_REQUEST'` to `ErrorCode` and `ERROR_TABLE` as `ErrorPolicy(400, False, False, 'The request is not valid.')`. The HTTP status stays for FastAPI until plan 2.
- Create: `backend/app/inner/__init__.py` (empty), `backend/app/inner/protocol.py`
- Test: `backend/tests/inner/__init__.py` (empty), `backend/tests/inner/test_protocol.py`

**Interfaces:**
- Produces, in `app/inner/protocol.py`:
  - `MAX_LINE_BYTES = 4096`
  - `@dataclass(frozen=True) class RawRequest: version: int; command: str; resource: str; args: dict[str, Any]`
  - `parse_request(line: bytes) -> RawRequest`. It raises `AppError('INVALID_REQUEST')` on: bad UTF-8, bad JSON, a non-object, `v` not exactly the int `1`, `command` or `resource` not a non-empty str, or `args` present but not a dict. A missing `args` becomes `{}`.
  - `encode_result(result: Any) -> bytes`
  - `encode_error(error: AppError, last_good: Any | None = None) -> bytes`

  Both encoders use compact JSON, `ensure_ascii=False`, UTF-8, and end with `\n`.

- [ ] **Step 1: Write the failing tests**
  - `test_parses_a_valid_request`: `parse_request(b'{"v":1,"command":"GET","resource":"posts","args":{"term":"x"}}\n')` == `RawRequest(1, 'GET', 'posts', {'term': 'x'})`.
  - `test_missing_args_is_an_empty_dict`.
  - `test_rejects_invalid_requests` (parametrized), each raising code `INVALID_REQUEST`:
    - `b'\xff\n'`, `b'not json\n'`, `b'[]\n'`, `b'null\n'`, `b'"x"\n'`;
    - `{"v":2,...}`, `{"v":"1",...}`, `{"v":true,...}`;
    - a missing `command`, `{"command":""}`, `{"resource":5}`, `{"args":[]}`.
  - `test_encode_result_is_one_compact_line`: `encode_result({'a': 'é'}) == '{"ok":true,"result":{"a":"é"}}\n'.encode()`.
  - `test_encode_error_carries_the_error_body_and_last_good`:
    - with `AppError('RATE_LIMITED', retry_after_seconds=30)` and `last_good={'x': 1}`, the decoded line equals `{'ok': False, 'error': to_error_body(err), 'lastGood': {'x': 1}}`;
    - with no `last_good`, there is no `lastGood` key.
  - `test_invalid_request_policy`: `AppError('INVALID_REQUEST')` has message `'The request is not valid.'`, `retryable is False` and `auto_retry is False`.
- [ ] **Step 2: Run, and confirm the failure**
  - Run: `.venv/bin/pytest tests/inner/test_protocol.py -q`
  - Expected: `ModuleNotFoundError: No module named 'app.inner'`.
- [ ] **Step 3: Implement** `protocol.py` and the `errors.py` entry. Use `json.loads` on the decoded line; `json.loads` is fine with a trailing `\n`.
- [ ] **Step 4: Run, and confirm everything passes**
  - Run: `.venv/bin/pytest tests/inner/test_protocol.py tests/test_errors.py -q`
  - Expected: all pass.
- [ ] **Step 5: Commit** with `feat(inner): add the line-based JSON wire protocol and INVALID_REQUEST`.

### Task 2: `LoopThread`, the event-loop bridge

**Files:**
- Create: `backend/app/inner/loop_thread.py`
- Test: `backend/tests/inner/test_loop_thread.py` (plain sync tests; no anyio marker)

**Interfaces:**
- Produces: `class LoopThread`.
  - `__init__()` starts a daemon thread running a new event loop.
  - `run(coro: Coroutine[Any, Any, T], timeout: float) -> T`
  - `call(fn: Callable[[], T], timeout: float) -> T`: runs `fn` on the loop thread.
  - `stop() -> None`: stops the loop and joins the thread. It's idempotent.
  - On timeout, `run` and `call` cancel the work and raise `AppError('UPSTREAM_TIMEOUT')`. Any other exception is re-raised unchanged in the caller.

- [ ] **Step 1: Write the failing tests**
  - `test_run_returns_the_coroutine_result`: `run(asyncio.sleep(0, 'x'), 1) == 'x'`.
  - `test_run_reraises_the_same_exception`: a coroutine raising `AppError('DB_ERROR')`; the caller gets that same object.
  - `test_run_times_out_with_upstream_timeout`: `run(asyncio.sleep(10), 0.05)` raises code `UPSTREAM_TIMEOUT` within 1 s.
  - `test_call_runs_on_the_loop_thread`: `call(threading.get_ident, 1)` equals the ident recorded by `run` of a coroutine returning `threading.get_ident()`, and differs from the test thread's ident.
  - `test_stop_is_idempotent_and_joins`: after `stop(); stop()` the thread is not alive.
- [ ] **Step 2: Run, and confirm the failure**
  - Run: `.venv/bin/pytest tests/inner/test_loop_thread.py -q`
  - Expected: `ModuleNotFoundError`.
- [ ] **Step 3: Implement.** Use `asyncio.run_coroutine_threadsafe(...).result(timeout)`. On `concurrent.futures.TimeoutError`, call `future.cancel()` and raise `AppError('UPSTREAM_TIMEOUT')`. `call` wraps `fn` in a coroutine.
- [ ] **Step 4: Run, and confirm everything passes** (same command).
- [ ] **Step 5: Commit** with `feat(inner): add LoopThread to run async work from worker threads`.

### Task 3: `Command`, `Dispatcher` and the `ResourceHandler` base

**Files:**
- Create: `backend/app/inner/dispatcher.py`, `backend/app/inner/handlers.py` (the base class only in this task)
- Test: `backend/tests/inner/test_dispatcher.py`

**Interfaces:**
- Produces, in `dispatcher.py`:
  - `@dataclass(frozen=True) class Command: verb: str; resource: str; args: Mapping[str, Any]`
  - `class CommandHandler(Protocol): def handle(self, command: Command) -> Any`
  - `class Dispatcher`:
    - `__init__(self, handlers: Mapping[str, CommandHandler])`
    - `handle(self, command: Command) -> Any`: an unknown resource raises `AppError('INVALID_REQUEST')`.
    - a property `resources -> frozenset[str]`
- Produces, in `handlers.py`: `class ResourceHandler`.
  - `handle(self, command: Command) -> Any` calls `get`, `post`, `put` or `delete` by `command.verb`.
  - Each of those methods takes `args: Mapping[str, Any]`, and by default raises `AppError('INVALID_REQUEST', 'This command is not supported for this resource.')`.
  - Any other verb raises `INVALID_REQUEST` with the same message.

- [ ] **Step 1: Write the failing tests**
  - `test_dispatches_to_the_resources_handler`: a fake handler records the commands it receives; dispatching `Command('GET', 'posts', {})` returns its result.
  - `test_unknown_resource_is_invalid_request`.
  - `test_resources_lists_the_handler_names`.
  - `test_resource_handler_calls_the_verb_method`: a subclass overriding `get` returns `args['x']` for `Command('GET', 'r', {'x': 1})`.
  - `test_unsupported_verbs_are_invalid_request` (parametrized over `POST`, `PUT`, `DELETE`, `PATCH`) on a subclass that overrides only `get`.
- [ ] **Step 2: Run, and confirm the failure**
  - Run: `.venv/bin/pytest tests/inner/test_dispatcher.py -q`
  - Expected: `ModuleNotFoundError`.
- [ ] **Step 3: Implement.** The verb-to-method mapping is a fixed dict `{'GET': 'get', 'POST': 'post', 'PUT': 'put', 'DELETE': 'delete'}`, so there's no `getattr` on user input.
- [ ] **Step 4: Run, and confirm everything passes.**
- [ ] **Step 5: Commit** with `feat(inner): add commands, the dispatcher and the resource handler base`.

### Task 4: `RequestNormalizer`, the first stage of the chain

**Files:**
- Create: `backend/app/inner/normalizer.py`
- Test: `backend/tests/inner/test_normalizer.py`

**Interfaces:**
- Consumes: `parse_request`, `encode_result` and `encode_error` (Task 1); `Command` and `CommandHandler` (Task 3); `Normalizer` from `app.terms.normalizer` (existing, `normalize(raw: str) -> str`).
- Produces: `class RequestNormalizer`.
  - `__init__(self, term_normalizer: Normalizer, next: CommandHandler, logger: logging.Logger)`
  - `handle(self, line: bytes) -> bytes`. It never raises:
    - It parses the line, uppercases `command`, and replaces a string `args['term']` with its normalized value. A `term` longer than 200 characters, or not a string, is `INVALID_TERM`.
    - It calls `next.handle(Command(...))` and returns `encode_result(result)`.
    - It catches an `AppError`, returning `encode_error(error, getattr(error, 'last_good', None))`.
    - Any other exception is logged with `exc_info` and returned as `encode_error(AppError('INTERNAL'))`.
  - `MAX_TERM_LENGTH = 200`.

- [ ] **Step 1: Write the failing tests.** Use a recording fake `next` and `TermNormalizer(PRESETS['reddit-subreddit'])`.
  - `test_normalizes_the_term_and_uppercases_the_verb`: the line `{"v":1,"command":"get","resource":"posts","args":{"term":" r/Ubisoft ","freshness":"live"}}` reaches `next` as `Command('GET', 'posts', {'term': 'ubisoft', 'freshness': 'live'})`, and the reply decodes to `{'ok': True, 'result': <next's return>}`.
  - `test_requests_without_a_term_pass_through`: the health line reaches `next` with `args == {}`.
  - `test_invalid_term_is_an_error_reply`: term `bad name!` → reply code `INVALID_TERM`, and `next` is not called.
  - `test_a_term_over_200_characters_is_invalid_term`: `'a' * 201`.
  - `test_a_non_string_term_is_invalid_term`: `{"term": 5}`.
  - `test_an_invalid_line_is_an_invalid_request_reply`: `b'[]\n'`.
  - `test_last_good_on_an_error_is_written`: `next` raises an `AppError` subclass instance with attribute `last_good = {'x': 1}` → the reply has `lastGood == {'x': 1}`.
  - `test_an_unexpected_exception_is_a_logged_internal_reply`: `next` raises `RuntimeError('secret')`. The reply has code `INTERNAL` and does not contain `'secret'`, and the log records `exc_info`.
- [ ] **Step 2: Run, and confirm the failure**
  - Run: `.venv/bin/pytest tests/inner/test_normalizer.py -q`
  - Expected: `ModuleNotFoundError`.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run, and confirm everything passes.**
- [ ] **Step 5: Commit** with `feat(inner): add the request normalizer stage`.

### Task 5: `PostsHandler` and `HealthHandler`

**Files:**
- Modify: `backend/app/inner/handlers.py`
- Test: `backend/tests/inner/test_handlers.py`

**Interfaces:**
- Consumes: `ResourceHandler` (Task 3); `LoopThread` (Task 2); the existing `CollectionService` (`collect(term, force)`, `get_posts(term)`, `last_good(term)`), `Repository.ping()`, `Config`.
- Produces:
  - `class CollectionFailed(AppError)`:
    - `__init__(self, error: AppError, last_good: dict | None)` copies `code`, `message`, `retry_after_seconds` and the effective `retryable`;
    - it has a `last_good` attribute and sets `__cause__ = error`.
  - `PostsHandler(service: CollectionService, loop: LoopThread, timeout_seconds: float)` with `get(args)`:
    - `freshness = args.get('freshness', 'auto')`; anything other than `auto`, `live` or `stored` raises `INVALID_REQUEST`;
    - it returns `CollectionResponse.model_dump(by_alias=True)`;
    - on an `AppError` from `auto` or `live`, it raises `CollectionFailed(error, last_good)`. `last_good` is `service.last_good(term)` dumped by alias, or `None`.
    - Every service call goes through `loop.run` or `loop.call` with `timeout_seconds`.
  - `HealthHandler(repository: Repository, config: Config, loop: LoopThread)` with `get(args)`. It returns `{'status': 'ok', 'db': 'ok', 'collectorMode': ..., 'staleAfterSeconds': ...}`; if `ping` raises an `AppError`, `status` and `db` are `'error'`.

- [ ] **Step 1: Write the failing tests.** Use a real `CollectionService` with `FakeCollector` and `memory_repository` from `tests/fakes.py`, `make_normalizer()` from `tests/helpers.py`, and a `LoopThread` fixture that is stopped on teardown.
  - `test_auto_collects_then_serves_the_cache`: two `get({'term': 'ubisoft'})` calls give `collection.source` `'live'` then `'cache'`, and `collector.calls` has length 1.
  - `test_live_always_collects`: `freshness='live'` twice gives two collector calls.
  - `test_stored_never_collects`: `freshness='stored'` on a never-collected term returns `{'collection': None, 'posts': []}`, and `collector.calls == []`.
  - `test_unknown_freshness_is_invalid_request`: `'soon'`.
  - `test_a_failure_carries_the_last_good_feed`: collect once, then set `collector.result = AppError('UPSTREAM_ERROR')`. A `live` get raises `CollectionFailed` with `code == 'UPSTREAM_ERROR'` and `last_good['collection']['term'] == 'ubisoft'`.
  - `test_a_failure_without_history_has_no_last_good`: `last_good is None`.
  - `test_a_hanging_collection_times_out`: `collector.hold()`, with `timeout_seconds=0.1` → code `UPSTREAM_TIMEOUT` within 1 s, then `collector.release()` in teardown. The `hold()` gate must be created on the loop thread: call `loop.call(collector.hold, 1)`.
  - `test_health_reports_mode_and_threshold` and `test_health_reports_a_database_error` (a repository whose `ping` raises `AppError('DB_ERROR')`).
- [ ] **Step 2: Run, and confirm the failure**
  - Run: `.venv/bin/pytest tests/inner/test_handlers.py -q`
  - Expected: `ImportError` for `PostsHandler`.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run, and confirm everything passes.**
- [ ] **Step 5: Commit** with `feat(inner): add the posts and health handlers`.

### Task 6: `ThreadPoolServer`

**Files:**
- Create: `backend/app/inner/server.py`
- Test: `backend/tests/inner/test_server.py` (real sockets on `127.0.0.1`, port 0)

**Interfaces:**
- Consumes: `MAX_LINE_BYTES`, `encode_error` (Task 1); anything with `handle(line: bytes) -> bytes`.
- Produces:
  - `class InnerServer(Protocol)`: `serve_forever() -> None`, `shutdown() -> None`, and a property `address -> tuple[str, int]`.
  - `class ThreadPoolServer`:
    - `__init__(self, host: str, port: int, threads: int, chain: LineHandler, logger: logging.Logger, read_timeout_seconds: float = 5.0)`. It binds in `__init__`, so `address` is known before serving.
    - `shutdown()` stops accepting, waits for running requests, and shuts the executor down.
  - `LineHandler = Protocol` with `handle(self, line: bytes) -> bytes`.

- [ ] **Step 1: Write the failing tests.** Add a helper `exchange(address, data: bytes | list[bytes]) -> bytes` that sends the chunk(s), half-closes writing only if asked, and reads until EOF. The server runs `serve_forever` in a thread from a fixture and is shut down on teardown.
  - `test_round_trip`: an echo chain returns `b'ok:' + line`; one request gets exactly that reply, and then the connection is closed (EOF).
  - `test_an_oversize_line_gets_invalid_request`: 5000 bytes without `\n` → a reply with code `INVALID_REQUEST`, and the chain is not called.
  - `test_a_silent_client_is_closed_without_a_reply`: with `read_timeout_seconds=0.2`, connect and send nothing → EOF with `b''` within 1 s.
  - `test_a_partial_line_then_close_gets_no_reply_and_frees_the_worker` (Review Focus 2): with `threads=1`, send `b'{"v":1'` and close; then a normal request on a new connection is answered.
  - `test_a_character_split_across_writes_is_reassembled` (Review Focus 3): send `'{"t":"é"}\n'.encode()` in two writes, split inside the `é` bytes; the chain receives the full line.
  - `test_more_connections_than_threads_are_all_answered` (Review Focus 5): with `threads=2` and a chain that sleeps 0.2 s, 6 concurrent clients all get replies.
  - `test_shutdown_waits_for_a_running_request`: a request whose chain sleeps 0.3 s; `shutdown()` is called mid-request and the client still receives its reply.
  - `test_a_chain_exception_is_an_internal_reply_not_a_crash`: the chain raises `RuntimeError`; the client gets code `INTERNAL`, and the next request is served.
- [ ] **Step 2: Run, and confirm the failure**
  - Run: `.venv/bin/pytest tests/inner/test_server.py -q`
  - Expected: `ModuleNotFoundError`.
- [ ] **Step 3: Implement.**
  - Build on `socketserver.TCPServer` with `allow_reuse_address = True`. Override `process_request` to submit `process_request_thread` to a `ThreadPoolExecutor(max_workers=threads)`.
  - The request handler sets `settimeout(read_timeout_seconds)` and reads with `rfile.readline(MAX_LINE_BYTES + 1)`. More than `MAX_LINE_BYTES` with no `\n` → an `INVALID_REQUEST` reply. EOF without `\n` or a timeout → close, no reply, logged at debug level.
  - It writes the chain's reply and closes. An exception from the chain → an `INTERNAL` reply, logged.
- [ ] **Step 4: Run, and confirm everything passes**
  - Run: `.venv/bin/pytest tests/inner/test_server.py -q`
  - Expected: all pass, within a few seconds.
- [ ] **Step 5: Commit** with `feat(inner): add the thread-pool TCP server`.

### Task 7: Presets, configuration, composition and the `python -m app.inner` entry point

**Files:**
- Create: `backend/app/inner/presets.py`, `backend/app/composition.py`, `backend/app/inner/__main__.py`
- Modify:
  - `backend/app/config.py`: the new settings.
  - `backend/app/collector/factory.py`: move `create_term_normalizer` to `composition.py` and update its imports in `main.py` and the tests.
  - `package.json`: `dev` starts a third process `inner` (`dev:inner`: `cd backend && .venv/bin/python -m app.inner`).
- Test: `backend/tests/test_config.py`, `backend/tests/inner/test_inner_end_to_end.py`, `backend/tests/test_collector.py` (move the `create_term_normalizer` test into `tests/test_composition.py`)

**Interfaces:**
- Consumes: everything from Tasks 1–6.
- Produces:
  - `SERVER_PRESETS: Mapping[str, type]` (`{'threadpool': ThreadPoolServer}`).
  - `INNER_ROUTE_PRESETS: Mapping[str, Mapping[str, str]]` (`{'collector': {'posts': 'posts', 'health': 'health'}}`, mapping a resource to a handler name). Both are read-only.
  - `Config` fields `inner_host: str`, `inner_port: int`, `server: str`, `server_threads: int`, `inner_routes: str`.
  - In `app/composition.py`:
    - `create_term_normalizer(config) -> TermNormalizer`
    - `build_inner(config: Config, *, logger: logging.Logger, collector: Collector | None = None) -> InnerApp`. The `collector` override is for tests.
    - `@dataclass class InnerApp: server: InnerServer; close: Callable[[], None]`. `close()` shuts down the server, the loop and the database, in that order, and is idempotent.
  - `build_inner` raises `ConfigError` if the routes preset names a handler that isn't built. The handlers built are `posts` and `health`.

- [ ] **Step 1: Write the failing tests**
  - Config:
    - defaults `inner_host == '127.0.0.1'`, `inner_port == 3002`, `server == 'threadpool'`, `server_threads == 8`, `inner_routes == 'collector'`;
    - rejected values that name the variable: `INNER_PORT=70000`, `SERVER=nope`, `SERVER_THREADS=0`, `SERVER_THREADS=65`, `INNER_ROUTES=nope`;
    - `INNER_PORT=0` is accepted.
  - `test_composition.py`:
    - `test_create_term_normalizer_uses_the_configured_preset` (moved);
    - `test_build_inner_refuses_a_route_to_a_missing_handler`: monkeypatch `INNER_ROUTE_PRESETS` with `{'collector': {'posts': 'nope'}}` → `ConfigError`.
  - `test_inner_end_to_end.py`: `build_inner` from `load_config({'COLLECTOR_MODE': 'fixture', 'DB_PATH': str(tmp_path / 'x.db'), 'INNER_PORT': '0'})`, `serve_forever` in a thread, `close()` on teardown, and requests sent as real lines:
    - `test_health_over_the_wire`: `result.collectorMode == 'fixture'`.
    - `test_auto_then_cached_then_live`: the sources are `live`, `cache`, `live` (for `freshness=live`), and the post ids are identical.
    - `test_stored_after_a_collection_returns_it`.
    - `test_fixture_failures_map_to_error_replies` (parametrized): `notfound` → `NOT_FOUND_SUBREDDIT` (not retryable); `ratelimited` → `RATE_LIMITED` with `retryAfterSeconds == 30`; `broken` → `UPSTREAM_ERROR`; `timeout` → `UPSTREAM_TIMEOUT`.
    - `test_a_failure_after_a_success_carries_last_good`: collect `ubisoft`, then with an injected `FakeCollector` whose result is `AppError('UPSTREAM_ERROR')`, a `live` request has `lastGood.collection.term == 'ubisoft'`. Use the `collector=` override.
    - `test_two_concurrent_auto_requests_share_one_collection`: an injected `FakeCollector`, `hold()` via the app's loop, two client threads, `release()`; `collector.calls` has length 1 and both replies have the same `collection.id`.
    - `test_python_m_app_inner_serves_and_refuses_bad_config`: a subprocess `python -m app.inner` with `INNER_PORT` set to a free port and fixture mode answers the health line. With `SERVER=nope` it exits non-zero with `Invalid configuration: SERVER` on stderr.
- [ ] **Step 2: Run, and confirm the failure**
  - Run: `.venv/bin/pytest tests/test_config.py tests/test_composition.py tests/inner/test_inner_end_to_end.py -q`
  - Expected: failures on the missing config fields and `ModuleNotFoundError` for `app.composition`.
- [ ] **Step 3: Implement.**
  - `build_inner` opens the database and applies the schema. It builds the repository, the collector (`create_collector`) unless one is injected, the service (with `create_term_normalizer`), the `LoopThread`, and the handlers with `timeout_seconds = config.collection_deadline_ms / 1000 + 5`. Then the dispatcher from the routes preset, `RequestNormalizer`, and `SERVER_PRESETS[config.server](config.inner_host, config.inner_port, config.server_threads, chain, logger)`.
  - `app/inner/__main__.py` loads the config (on a `ConfigError`, print it to stderr and exit 1), sets up logging as `main.run` does, and calls `build_inner`. It logs `inner server listening on host:port`, installs SIGINT and SIGTERM handlers that call `server.shutdown()` from a helper thread, runs `serve_forever()`, and finally calls `close()`.
- [ ] **Step 4: Run the full suite and checks**, from the repo root:

  ```bash
  npm test
  npm run lint
  scripts/check-secrets.sh
  scripts/check-compliance.sh
  ```

  Expected: every test passes, lint is clean, and both checks print OK.

  Then a manual check: start `COLLECTOR_MODE=fixture npm run dev` and send `printf '{"v":1,"command":"GET","resource":"posts","args":{"term":"ubisoft"}}\n' | nc 127.0.0.1 3002`. Expected: one JSON line with 7 posts, while the UI at :5173 still works through FastAPI.
- [ ] **Step 5: Commit** with `feat(inner): wire the inner server from config and run it with python -m app.inner`.
