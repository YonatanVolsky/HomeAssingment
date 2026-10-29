# 06 Testing and integration

## Goal and dependencies

Make sure the parts work together, prove the key behaviors, and have a repeatable
acceptance and demo script. Unit tests are written inside each component branch
(see their files); this component adds cross-component checks, the smoke test,
and the acceptance checklist. Depends on `02` to `05`.

## Test strategy

Small, focused, offline by default. The live Reddit call is opt-in.

| Layer | Tool | Scope | Where defined |
|---|---|---|---|
| Unit: collector | Vitest | normalizeTerm, mappers, parseListing, classifier, token provider, client retries (mock undici) | 02 |
| Unit: db | Vitest, `:memory:` and temp file | upsert, atomicity, ordering, scoping | 03 |
| API | Vitest + `app.inject()` | status codes, error mapping, cache, in-flight, no leaks | 04 |
| UI | Vitest + Testing Library | reducer, formatters, cards, states, a11y roles | 05 |
| Integration | Vitest, real SQLite file + fixture collector | full POST then GET then restart | this file |
| Live smoke | `LIVE=1` | one real collection for `ubisoft` | 02 |
| Smoke script | bash + curl | running server end to end | this file |
| Manual acceptance | checklist | demo script | this file |

Coverage is not a target; the matrix below is.

## Requirement-to-test matrix

| Requirement | Test | Layer |
|---|---|---|
| Valid mobile response maps correctly | parse `listing-new-ok` | collector |
| Missing/deleted author handled | `listing-deleted-author` gives `author: null` | collector |
| Invalid response shape fails explicitly | `listing-malformed` gives `CONTRACT_ERROR` | collector |
| Non-success status fails explicitly | 5xx, 4xx, 429 each map to the right code | collector |
| Timestamp conversion | known epoch to expected ISO | collector |
| Permalink normalization | relative, absolute, foreign host rejected | collector |
| Result limit | 30 nodes, limit 25 gives 25 | collector |
| Blank/malformed term | table in 02 | collector |
| Token reuse and single refresh | mock agent call counts | collector |
| 429 not retried, has `retryAfterSeconds` | | collector |
| Collection stops at the deadline | repeated timeouts give `UPSTREAM_TIMEOUT` within `COLLECTION_DEADLINE_MS` | collector |
| Fixture mode is isolated | fixture collections land in `data/fixture.db` only | api |
| Duplicate IDs upserted | run twice, row count unchanged, counts updated | db |
| Ordering deterministic | equal timestamps ordered by `reddit_id` | db |
| Term scoping | two terms, each feed contains only its posts | db |
| Failed run keeps old feed | failure after success | db |
| Shared post across terms | one row, two links | db |
| Transactional write | injected failure leaves nothing | db |
| Invalid request gives 400 | | api |
| Success persists and returns posts | | api |
| Empty result is 200 with `posts: []` | | api |
| Collector failure is a safe structured error | no stack, no headers | api |
| DB failure is not a success | `DB_ERROR` 500 | api |
| TTL cache and `force` | call counts, `source` | api |
| Concurrent same-term requests share one call | | api |
| Persistence survives restart | new app instance, same file, GET returns feed | integration |
| Reload shows same feed | GET equals last POST posts | integration |
| Reducer transitions | table in 05 | ui |
| Unsafe link not rendered | `javascript:` and foreign host | ui |

## Step-by-step plan

1. Work on `feat/app` (last commits before it is merged).
2. **Integration test**: build the app with a temp-file DB and the fixture
   collector; POST, GET, close and reopen the app on the same file, GET again;
   POST twice and assert no duplicate posts.
3. **Failure integration test**: collector stub throws; assert a failed run is
   stored and `lastGood` is returned.
4. **Smoke script** `scripts/smoke.sh`: against a running server, checks
   `/api/health`, collects `ubisoft` (or the fixture), repeats to confirm
   `source: "cache"`, `force` to confirm `live`, an invalid term for 400, and
   prints a short pass/fail summary. Exit code non-zero on failure.
5. **Fixture-mode demo check**: `COLLECTOR_MODE=fixture npm run dev` shows the
   offline banner in the UI, and `data/collector.db` is unchanged afterwards.
6. **Manual acceptance** run (below), recording results in `docs/acceptance.md`
   with date and tool versions.
7. **Bug fixing** buffer (part of the 40 min).
8. **Static checks**: `grep` for forbidden usage (see below) added to
   `scripts/check-compliance.sh`, run in the merge checklist.
9. Run the merge checklist and merge `feat/app` into `main`.

## Entities

### `scripts/smoke.sh`

Inputs: `BASE_URL` (default `http://127.0.0.1:3001`), `TERM` (default `ubisoft`).
Checks and expected results:

| Check | Expectation |
|---|---|
| `GET /api/health` | 200, `db: ok` |
| `POST` blank term | 400 `INVALID_TERM` |
| `POST` valid term | 200, `posts.length >= 1` (or `0` allowed with a warning for fixtures) |
| `POST` same term immediately | 200, `source: "cache"` |
| `POST` with `force: true` | 200, `source: "live"` (skipped in fixture mode) |
| `GET /api/posts?term=` | 200, same post ids as the last POST |

### `scripts/check-compliance.sh`

Scans source and dependency manifests only: `backend/src`, `frontend/src`,
`packages/`, `scripts/` and every `package.json` and `package-lock.json`.
Excludes `plan/`, `docs/`, `README.md`, `DESIGN.md`, `node_modules/` and the
script itself, because those legitimately name the forbidden tools. Fails, with
file and line, on case-insensitive whole-word matches (`grep -Ewi` with `\b`
boundaries, so words like "sprawl" do not match) of:
`selenium`, `puppeteer`, `playwright`, `praw`, `snoowrap`, `reddit.com/dev/api`,
and the public JSON listing pattern `reddit\.com/r/[^ ]*\.json`.

`oauth.reddit.com` and the token endpoint are **not** on the deny-list by
default: the mobile app may use them with its own credentials. Instead, the
script prints every Reddit host found in `backend/src` and checks it against an
allow-list taken from the spec (01). An unexpected host fails the check. Each
allow-list entry has a comment pointing to the spec section that explains why
it is app traffic.

Exists so the "no browser automation, no official API" claim is mechanically
checked and can be shown in the interview.

### Manual acceptance checklist (`docs/acceptance.md`)

1. Fresh clone, follow the README exactly, app starts.
2. Search `ubisoft`: loading, then a feed of cards.
3. Open a card's link: the correct Reddit post opens in a new tab.
4. Inspect the DB (`scripts/db-inspect.sh`): posts and one collection row exist.
5. Reload the page and restore the term: same feed, `cached` badge.
6. Search again within 60 s: `cached`. Click Refresh: `live`, and the DB has
   a second collection row but **no duplicate posts**.
7. Search an empty or tiny subreddit: empty state with guidance.
8. Search `r/a`, `bad name!` or blank: validation message. Search a
   well-formed name that does not exist: "not found" message, no Retry button.
9. Stop the backend and search: network error state.
10. Simulate failure (invalid token env or fixture error mode): error banner,
    previous feed still shown.
11. Run the full test suite: green.

### Demo script (also used in the interview)

Follows steps 2 to 6, with the request path narrated: form, Vite proxy,
`POST /api/collections`, `CollectionService`, token and listing requests,
parse, SQLite transaction, `GET`-style read back, render. Keep the HTTP Toolkit
capture of the original app traffic open next to the replayed request to show
the equivalence.

## Version control plan

- Branch: `feat/app`.
- Commits, in order:
  1. `test: add integration test for persistence across restart`
  2. `test: add failure-path integration test with lastGood`
  3. `chore(scripts): add smoke script`
  4. `chore(scripts): add compliance grep check`
  5. `docs: record acceptance run results`
  6. `fix: <issues found>` (one commit per bug, each with a regression test)
- Merge criteria: acceptance checklist 1 to 11 complete on this machine; smoke
  script green against live mode.
- Bugs found here are fixed on `feat/app` with a failing test first.

## Definition of done

- [ ] `npm test` is green offline; `npm run test:live` was run once and passed.
- [ ] Smoke script passes against the running app.
- [ ] Compliance script passes.
- [ ] Acceptance checklist recorded with date and versions.
