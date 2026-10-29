# 02 Collector

## Goal and dependencies

A self-contained module that turns a term into a list of normalized `Post`
objects by calling Reddit's mobile endpoints directly. It knows nothing about
the database, the cache, or HTTP routes. Depends on `00` (config, errors,
contracts) and `01` (spec and fixtures). The exact GraphQL/request details are
filled in from `docs/reddit-mobile-request.md`; everything below that is
independent of them is fixed now.

## Boundaries

- In: a normalized subreddit name, a limit.
- Out: `Post[]` or a thrown `AppError`.
- Not here: caching of results, in-flight de-duplication, persistence
  (those are in 04), and any logging of tokens or headers.

## Step-by-step plan

1. Work on `feat/app` (after the 00 commits).
2. **`normalizeTerm`** with tests first (pure, no network).
3. **Mappers** (`toIsoUtc`, `toAbsolutePermalink`, `truncatePreview`, `mapAuthor`)
   with tests first.
4. **Raw schema** (`RawListingSchema`, zod) built from the fixtures; test that
   each fixture parses or fails as expected.
5. **`parseListing`**: raw JSON to `Post[]`, skipping non-post nodes, stopping at
   `limit`. Tests per fixture.
6. **Error classification** (`classifyResponse`): status, headers, body to
   `AppError`. Tests for 401/403, 404, 429 (with `Retry-After`), 5xx.
7. **`TokenProvider`**: fetch, cache until `expiresAt - 60s`, single-flight
   refresh. Tests with a mocked undici agent.
8. **`RedditClient.fetchNewPosts`**: build request, send with timeouts, retry
   policy, one token refresh on 401/403, classify, parse, all under one
   collection deadline. Tests with mock agent, including a deadline test.
9. **`createCollector(config)`** facade that wires 7 and 8 and exposes
   `collect(subreddit, limit)`.
10. **Fake collector** (`createFixtureCollector`) that reads fixtures, used by
    04 and 06 for offline development and the fallback demo (clearly labelled
    offline when active).
11. **Optional live test** (`LIVE=1 npm run test:live`) calling real Reddit once
    for `ubisoft`. Excluded from the default test run.
12. Tick the definition of done below (merge happens with the rest of `feat/app`).

## Entities

### `normalizeTerm(input: string): string`

Pure. Returns the bare lowercase subreddit name or throws `AppError(INVALID_TERM)`.

| Input | Output |
|---|---|
| `ubisoft` | `ubisoft` |
| `r/Ubisoft`, `/r/Ubisoft/`, `  R/UBISOFT  ` | `ubisoft` |
| `https://www.reddit.com/r/ubisoft/` | `ubisoft` (accepted for convenience) |
| empty, whitespace, `r/` | throws |
| `de`, `gg` (2 chars) | accepted; a few real legacy subreddits are this short |
| `a` (1 char), over 21 chars, characters outside `[A-Za-z0-9_]` | throws |

The local check only rejects names that can never be valid. Whether a
well-formed name exists is left to Reddit, and its "not found" answer becomes
`NOT_FOUND_SUBREDDIT`.

Lowercasing is for storage and cache keys; Reddit names are case-insensitive.
The display name returned by Reddit stays in `Post.subreddit`.

### Mappers (pure)

| Function | Behavior |
|---|---|
| `toIsoUtc(value)` | Accepts the unit found in capture (epoch seconds, epoch ms, or ISO string). Returns ISO UTC. Throws `CONTRACT_ERROR` if not a valid date, so bad data is never stored |
| `toAbsolutePermalink(value)` | If relative (`/r/x/comments/...`) prefix `https://www.reddit.com`. If absolute, require host `reddit.com` or `*.reddit.com`, force `https`. Otherwise throws. Strips tracking query params |
| `truncatePreview(text)` | Collapses whitespace, strips markdown/HTML noise minimally, truncates to 300 chars on a word boundary with `…`. Empty result becomes `null` |
| `mapAuthor(value)` | Deleted, removed, or missing author becomes `null` |
| `mapFlair(value)` | Display text only; empty becomes `null` |

### `RawListingSchema` and `parseListing`

- `RawListingSchema` (zod) validates only the path to the post list and the
  fields we read. Unknown fields are ignored (`passthrough` off, strip).
- `parseListing(json, limit): Post[]`:
  1. Validate the envelope; failure throws `CONTRACT_ERROR`.
  2. Iterate nodes in order; skip promoted/ad nodes and nodes without an id.
  3. Map each node. A node missing a **required** field (id, title,
     created time, permalink) is skipped and counted; if **every** node is
     skipped while some existed, throw `CONTRACT_ERROR` (likely a schema
     change, not an empty subreddit).
  4. Stop at `limit`.
  5. Zero nodes with a valid envelope returns `[]` (a successful empty result).
- De-duplicates by `id` within one page.

### `TokenProvider`

| Member | Behavior |
|---|---|
| `get(): Promise<string>` | Returns cached token if `now < expiresAt - 60s`; otherwise refreshes |
| `invalidate()` | Drops the cached token (called after a 401/403) |
| internal in-flight promise | Concurrent callers share one refresh request |
| failure | Throws `UPSTREAM_AUTH`; failures are not cached |
| logging | Never logs the token; logs only "token refreshed, valid for N s" |

### `RedditClient`

| Member | Behavior |
|---|---|
| constructor deps | `config`, `TokenProvider`, undici `Agent` (keep-alive, `connect` timeout, `headersTimeout`, `bodyTimeout` all from `REQUEST_TIMEOUT_MS`), injectable `sleep` and `now` for tests |
| `fetchNewPosts(subreddit, limit): Promise<Post[]>` | Runs the flow below |

Flow: create one `AbortSignal.timeout(COLLECTION_DEADLINE_MS)` for the whole
collection, then get token, send listing request, classify response, parse.
The signal is passed to every request (token and listing) and to `sleep`, so
nothing outlives the deadline.

Retry policy (`withRetry`). This is the collector's **internal** auto-retry;
it must match the "Auto-retry in collector" column of the error table in 00,
and `AppError.retryable` (what the UI is told) is a separate concept:

| Failure | Retry? |
|---|---|
| Network reset, DNS failure, timeout | Yes, up to 2 retries, delay `250ms * 2^n` plus jitter |
| 5xx | Yes, same policy |
| 401/403 | Once, after `invalidate()` and a token refresh. If it fails again: `UPSTREAM_AUTH` |
| 429 | No. Throw `RATE_LIMITED` with `retryAfterSeconds` from the header (default 30) |
| Other 4xx | No. `UPSTREAM_ERROR`, or `NOT_FOUND_SUBREDDIT` where capture shows that signal |
| Content type not JSON, or body not parseable | No. `CONTRACT_ERROR` |
| Retries exhausted | `UPSTREAM_TIMEOUT` if the last failure was a timeout, else `UPSTREAM_ERROR` |
| Collection deadline reached (any phase) | No more attempts. `UPSTREAM_TIMEOUT` |
| Next backoff would end after the deadline | Skip the retry and throw the last error now |

Worst-case time is bounded by `COLLECTION_DEADLINE_MS` (25 s default), not by
multiplying per-request timeouts: without a deadline, token + 3 listing
attempts + a 401 refresh + 3 more attempts could exceed a minute. The UI
client timeout (05) is the deadline plus 10 s. Fastify's `requestTimeout` only
limits receiving the request body and does not bound handler time, so the
deadline must live here.

Request headers: exactly the minimal set from the spec. The `Authorization`
value is built at call time and never stored in logs, errors, or `cause`
objects that get serialized.

### `createCollector(config)` and the interface

```ts
interface Collector {
  collect(subreddit: string, limit: number): Promise<Post[]>
}
```

`createFixtureCollector(fixturesDir)` implements the same interface from
fixtures. The server picks it only when `COLLECTOR_MODE=fixture` is set. It is
never the default. Two safeguards keep sample data from looking real:
`/api/health` reports `collectorMode: "fixture"` (the only place the mode is
exposed; the UI shows an "Offline sample data" banner from it), and fixture
mode uses its own database file (`data/fixture.db`, see the config table in 00).

## Version control plan

- Branch: `feat/app`.
- Commits, in order (tests in the same commit as the code):
  1. `feat(collector): add normalizeTerm`
  2. `feat(collector): add field mappers`
  3. `feat(collector): add raw listing schema and parseListing`
  4. `feat(collector): classify upstream responses into AppError`
  5. `feat(collector): add token provider with single-flight refresh`
  6. `feat(collector): add reddit client with timeouts and retry policy`
  7. `feat(collector): add collector facade and fixture collector`
  8. `test(collector): add opt-in live smoke test`
- Done when: all collector tests pass offline; the live test passes once
  manually and the result is noted in the commit message of commit 8.
- If Reddit changes between capture and submission, only `RawListingSchema`,
  the request builder, and fixtures should need to change; keep that boundary.

## Definition of done

- [ ] `collect("ubisoft", 25)` returns real posts live (manual).
- [ ] No token, header, or raw body can appear in any thrown error message.
- [ ] Every row in the retry table has a test.
- [ ] A test proves a collection that keeps timing out stops at
      `COLLECTION_DEADLINE_MS` with `UPSTREAM_TIMEOUT`.
- [ ] A test asserts that the auto-retry decision and `AppError.retryable`
      agree with the table in 00 for every error code.
- [ ] `parseListing` is pure and has no import of undici or config.
- [ ] No use of official API hosts, browser automation, or PRAW anywhere
      (checked with a grep in the merge checklist).
