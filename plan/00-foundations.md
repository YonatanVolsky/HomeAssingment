# 00 Foundations

## Goal and dependencies

Create the repository skeleton, tooling, configuration, error model and shared
contracts so every other component starts from the same conventions.
No dependencies. Everything else depends on this.

## Repository layout (target)

```
.
├── README.md                     (07)
├── DESIGN.md                     (07)
├── WORKPLAN.md                   summary + links to plan/
├── plan/                         these files
├── package.json                  workspaces, root scripts
├── tsconfig.base.json
├── .nvmrc  .gitignore  .env.example  .editorconfig
├── scripts/
│   ├── check-secrets.sh
│   ├── check-compliance.sh       (06)
│   ├── scrub-fixture.mjs         (01)
│   └── smoke.sh                  (06)
├── docs/
│   └── reddit-mobile-request.md  (01)
├── captures/                     ignored, raw sniffer output
├── data/                         ignored, SQLite file
├── packages/contracts/           types only
│   └── src/index.ts
├── backend/
│   ├── src/
│   │   ├── config.ts
│   │   ├── errors.ts
│   │   ├── server.ts             entrypoint
│   │   ├── app.ts                buildApp(deps) for tests
│   │   ├── collector/            (02)
│   │   ├── db/                   (03)
│   │   ├── services/             (04)
│   │   └── routes/               (04)
│   └── test/ (fixtures/, unit/, integration/)
└── frontend/                     (05)
```

## Step-by-step plan

1. **Branch** `feat/app` from `main` (after `docs/plan` is merged). These are
   its first commits.
2. **Root package**: `package.json` with `"workspaces": ["backend", "frontend", "packages/*"]`,
   `engines.node >=22`, `.nvmrc` with `22`. Backend dev script uses `tsx watch`;
   root `dev` runs backend and frontend with `concurrently`.
3. **TypeScript base**: `tsconfig.base.json` (strict, `noUncheckedIndexedAccess`,
   ES2022, `moduleResolution: bundler` for frontend, `NodeNext` for backend via
   per-package overrides).
4. **Contracts package**: `packages/contracts/src/index.ts` with the types below.
   Type-only, imported with `import type`, so it needs no build step. In this
   same commit, prove that both the NodeNext backend and the bundler-mode
   frontend typecheck an import from it. If that takes more than 10 minutes,
   fall back to one `types.ts` file referenced by relative path from both.
5. **Lint and format**: ESLint (typescript-eslint, recommended) and Prettier
   (or `.editorconfig` only if time is short). Root scripts: `lint`, `typecheck`,
   `test`, `dev`, `build`.
6. **Config module** (`backend/src/config.ts`): zod-parsed env with defaults,
   fails fast with a readable message on invalid values.
7. **Error model** (`backend/src/errors.ts`): `AppError` and the error code table.
8. **`.env.example`** with every variable, no secrets.
9. **Git hygiene**: `.gitignore`, `scripts/check-secrets.sh` (run by hand, no hook).
10. **Verify**: `npm install`, `npm run lint`, `npm run typecheck`, `npm test`
    (zero tests is allowed, the runner must exit 0).

## Entities

### Contracts (`packages/contracts/src/index.ts`)

All timestamps are ISO 8601 UTC strings. All counts are non-negative integers.

| Type | Field | Type | Notes |
|---|---|---|---|
| `Post` | `id` | string | Reddit fullname, e.g. `t3_abc123`. Stable identity |
| | `title` | string | Required. Never empty (fall back to `(untitled)`) |
| | `author` | string or null | `null` for deleted or anonymous. UI shows "[deleted]" |
| | `commentCount` | number | |
| | `score` | number | May be negative |
| | `createdAt` | string | From Reddit's creation time |
| | `permalink` | string | Absolute `https://www.reddit.com/...` |
| | `subreddit` | string or null | Without the `r/` prefix |
| | `previewText` | string or null | Plain text, truncated to 300 chars with an ellipsis |
| | `flair` | string or null | Display text only |
| `CollectionSummary` | `id` | number | Always a successful run; failed runs are stored but never returned as a summary |
| | `term` | string | Normalized |
| | `source` | `"live"` or `"cache"` | `cache` means served from DB without calling Reddit |
| | `collectedAt` | string | `finished_at` of the run that produced the feed |
| | `postCount` | number | |
| `CollectionResponse` | `collection` | `CollectionSummary` or null | `null` only on `GET /api/posts` when the term was never collected |
| | `posts` | `Post[]` | Newest first |
| `ErrorCode` | | union | See the error table |
| `ErrorResponse` | `error.code` | `ErrorCode` | |
| | `error.message` | string | Safe for display, no internals |
| | `error.retryable` | boolean | Whether the UI should offer "Try again". From the error table |
| | `error.retryAfterSeconds` | number, optional | Only for `RATE_LIMITED`; the retry button waits this long |
| | `lastGood` | `CollectionResponse`, optional | Previous successful feed for the term, so the UI can keep showing it |
| `CollectRequest` | `term` | string | |
| | `force` | boolean, optional | Bypasses the result cache |

### Config (`backend/src/config.ts`)

| Variable | Default | Validation | Used by |
|---|---|---|---|
| `PORT` | `3001` | int 1-65535 | server |
| `HOST` | `127.0.0.1` | string | server. Local only by design |
| `COLLECTOR_MODE` | `live` | `live` or `fixture` | server picks the collector (02, 04) |
| `DB_PATH` | `./data/collector.db`, or `./data/fixture.db` when `COLLECTOR_MODE=fixture` | string, parent dir created | db. Separate files so sample data never mixes with real data |
| `MAX_POSTS` | `25` | int 1-100 | collector |
| `COLLECTION_TTL_SECONDS` | `60` | int 0-3600. `0` disables the cache | service |
| `STALE_AFTER_SECONDS` | `600` | int >= 1 | exposed to UI via `/api/health` (see 04) |
| `REQUEST_TIMEOUT_MS` | `8000` | int 1000-20000, must be below `COLLECTION_DEADLINE_MS` | collector, per HTTP request |
| `COLLECTION_DEADLINE_MS` | `25000` | int 5000-60000 | collector. Hard limit for one whole collection, including token, retries and refresh. The UI timeout (05) is this plus 10 s |
| `REDDIT_*` | decided in 01 | every one has a working default | collector. The app must run with **no** Reddit-specific setup; values taken from the app (user agent, public client id) are defaults in code, documented in the spec |
| `LOG_LEVEL` | `info` | pino levels | server |

Behavior: parse once at startup, export a frozen object, never read
`process.env` anywhere else.

### Error model (`backend/src/errors.ts`)

`class AppError extends Error { code: ErrorCode; httpStatus: number; retryable: boolean; retryAfterSeconds?: number; cause?: unknown }`

`httpStatus` and `retryable` are derived from `code` by a single lookup table in
`errors.ts`; callers pass only the code, message, and optional cause or
`retryAfterSeconds`.

Messages are written for end users. `cause` holds the low-level error for logs
and is never serialized.

There are two separate retry notions, kept apart on purpose:

- **Auto-retry**: the collector re-sends the request itself, internally, before
  giving up. The test is "can the same request plausibly give a different
  result?" Only transient failures qualify.
- **`retryable`** (sent to the UI): whether the "Try again" button is offered.
  The test is "could the user doing nothing but waiting or clicking again
  succeed?" If the input must change, it is `false`.

| Code | HTTP | Auto-retry in collector | `retryable` (UI) | Raised when | User-facing message (summary) |
|---|---|---|---|---|---|
| `INVALID_TERM` | 400 | No (never reaches Reddit) | `false` | Blank, too long, or not a valid subreddit name | "Enter a subreddit name like r/ubisoft" |
| `RATE_LIMITED` | 429 | No. Retrying makes the block worse | `true`, but only after `retryAfterSeconds` | Reddit returns 429 | "Reddit is limiting requests. Try again in N seconds" |
| `UPSTREAM_AUTH` | 502 | Once, after a token refresh | `true` | Token fetch fails, or 401/403 persists after one refresh | "Could not authenticate with Reddit" |
| `UPSTREAM_ERROR` | 502 | Yes, up to 2 times with backoff (5xx and network errors only) | `true` | Reddit 5xx or network failure after retries, or an unexpected 4xx (not retried) | "Reddit is unavailable right now" |
| `UPSTREAM_TIMEOUT` | 504 | Yes, up to 2 times with backoff, while the collection deadline allows | `true` | Connect or response timeout after retries, or `COLLECTION_DEADLINE_MS` reached | "Reddit took too long to respond" |
| `NOT_FOUND_SUBREDDIT` | 404 | No | `false` | Reddit says the subreddit does not exist or is private/banned | "r/x was not found or is not public" |
| `CONTRACT_ERROR` | 502 | No. Deterministic: same request, same shape | `true` (may be a transient bad response, but likely a schema change) | Response does not match the expected shape | "Reddit returned an unexpected response" |
| `DB_ERROR` | 500 | No. Transactions are atomic, so a manual retry is safe | `true` | Any SQLite failure | "Could not save results locally" |
| `INTERNAL` | 500 | No | `true` | Anything else | "Something went wrong" |

`retryable` and `retryAfterSeconds` are set by `AppError` from this table, so
the rule lives in one place. The collector's retry policy (02) and the UI's
retry button (05) both follow it and must not hard-code their own code lists.

The frontend also defines a client-only code `NETWORK` (backend unreachable or
request timed out), always `retryable: true`. The backend never sends it, so it
is not in `ErrorCode`.

### Git helpers

- `scripts/check-secrets.sh`: exit 1 if tracked or staged files contain a
  token-shaped value (patterns and exclusions in the plan index, "Secrets and
  sensitive files"). Matches values, not words, so code that builds an
  `Authorization` header from a variable passes. Prints file and pattern, never
  the matched value. Run by hand; no git hook.

## Version control plan

- Branch: `feat/app` (first commits on it).
- Commits, in order:
  1. `chore: add root workspace, tsconfig base, nvmrc, gitignore`
  2. `feat(contracts): add shared API types`
  3. `chore: add eslint and prettier configuration`
  4. `feat(config): add validated environment config and .env.example`
  5. `feat(config): add AppError and error code table`
  6. `chore(scripts): add secret check script`
- Done when: `npm install`, `lint`, `typecheck`, `test` all exit 0 on a fresh
  clone. No tag.

## Definition of done

- [ ] Fresh clone installs and runs `npm run typecheck` and `npm test` cleanly.
- [ ] Every env var is in `.env.example` and in the config table above.
- [ ] Error code table matches `ErrorCode` in contracts.
- [ ] `.gitignore` covers captures, DB files and env files.
- [ ] `check-secrets.sh` passes on a file that builds an `Authorization` header
      from a variable and fails on a fixture containing a fake JWT.
