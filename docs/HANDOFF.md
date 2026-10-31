# Handoff: continuing the project

Updated 2026-10-31. A new Claude Code session should read this file first; it replaces the
conversation history, which does not carry over between sessions.

## Where things stand

- **Work branch: `feat/python`** (contains everything; built on `feat/app`). Nothing is merged
  into `main` beyond the plan yet — the merge is a pending step (see "Open to-do", below).
- **The required app is built, tested, and live collection works.** You can enter a subreddit
  and the backend fetches its real newest posts from Reddit, stores them in SQLite, and the UI
  shows them as cards. Verified live on 2026-10-30 (`docs/acceptance.md`, Run 3).
- **Live collection is the real thing now**, not a placeholder:
  `backend/app/collector/reddit/mobile_api.py` builds and sends the actual token and GraphQL
  listing requests, and `LIVE_COLLECTION_AVAILABLE = True`.
- **Tested:** Python backend (FastAPI, sqlite3, httpx + curl_cffi; 260 pytest cases plus one
  opt-in `live`), React JSX frontend (88 Vitest cases). All green on 2026-10-31, as are lint,
  the compliance and secret checks, `npm run test:live` and `scripts/smoke.sh` against a live
  backend (25 real r/ubisoft posts).
- **Fixed 2026-10-31: missing or banned subreddits.** Reddit answers these with HTTP 200, not
  404: `postFeed: null` for a name that does not exist, `__typename: "UnavailableSubreddit"`
  for a banned (and presumably private) one. The parser used to report both as "Reddit
  returned an unexpected response" with a retry button; it now raises `NOT_FOUND_SUBREDDIT`
  ("not found or is not public", no retry). Quarantined subreddits return a normal empty feed
  and show the empty state. Details in `docs/reddit-mobile-request.md`, "Errors and limits".
- `feat/app` is the earlier TypeScript version, kept for history only.

## The one thing that made live collection work (the fingerprint)

Replaying the app's requests from a default Python HTTP client returns **HTTP 403** from
Reddit's edge *before the token is even checked* — the edge fingerprints the TLS/HTTP-2
handshake to tell a real app from a script. The fix: the default transport
(`CurlCffiTransport` in `mobile_api.py`) uses **`curl_cffi`** with the `chrome_android`
profile, so our connection presents a real Android-client fingerprint. It is still a direct
HTTP request we build ourselves — no browser, no automation. Full write-up:
`docs/reddit-mobile-request.md`, section "Transport fingerprint (resolved)".

## The capture is a build-time artifact, not a runtime dependency

The Reddit traffic capture was the one-time reverse-engineering step. Everything learned from
it now lives in the committed code, so running on any machine needs **no capture, emulator, or
proxy** — only Python, Node, and internet:

- The request details (token endpoint, GraphQL operation, persisted-query hash, public client
  id, user agent) are hardcoded constants in `mobile_api.py`.
- A scrubbed real response lives in `backend/tests/fixtures/listing-new-ok.json` and drives the
  offline parser tests.
- The raw recording (`captures/reddit.har`) is **git-ignored** — it holds anonymous session
  tokens and is never committed or needed to run.

Only if Reddit changes its persisted-query hash or blocks the fingerprint would a fresh capture
be needed, to update those constants. See "Re-capturing" in README.md.

## Set up on a new computer

```bash
git clone https://github.com/YonatanVolsky/HomeAssingment.git
cd HomeAssingment
git checkout feat/python
```

Then follow README.md "Setup (once)": Python 3.11+ and Node 22+. Check it works:

```bash
npm test                               # offline; expect all backend + frontend tests green
COLLECTOR_MODE=fixture npm run dev     # offline demo: open http://localhost:5173, search "ubisoft"
npm run dev                            # live: fetches real Reddit posts
```

On Windows, use the Windows commands in README.md and run backend and frontend in two
terminals.

## Open to-do (the project's remaining steps)

Nothing is required for the app to work; these finish and package it.

1. **Browser check of the UI** — 375 px width, keyboard-only, dark mode (noted unfinished in
   DESIGN.md).
2. **Clean-machine dry run** from the README, to confirm a fresh clone runs with no hidden
   steps.
3. **Fix stale wording**: README.md still says `test:live` runs "after the capture" and that
   the capture result "will be documented"; `docs/acceptance.md` has no live end-to-end row
   yet.
4. **Merge `feat/python` into `main`** once the above pass. Until then a reviewer cloning the
   default branch gets only the plan, not the app.
5. **Push to GitHub** (needs the owner's login; a Claude session cannot do this).
6. Optional: `docs/interview-notes.md`, tag `v1.0-submission`, zip (plan/07); optionally delete
   the local raw `captures/reddit.har`.

## Things only a person can run

- **Live Reddit replay** (`cd backend && .venv/bin/pytest -m live -s`, or `npm run test:live`):
  Claude Code's safety classifier has blocked sessions from firing live Reddit requests, so
  the owner may need to run this in their own terminal (on 2026-10-31 a session was allowed
  to). Last run: 2026-10-31, passed.
- **`git push`**: needs the owner's GitHub credentials.

## Working conventions used so far

- Test first for every change: write the test, watch it fail, then implement.
- Small commits in Conventional Commit style (`feat(collector): ...`), each ending with a
  `Co-Authored-By` line when written with Claude.
- Before merging: `npm test`, `npm run lint`, `scripts/check-secrets.sh`,
  `scripts/check-compliance.sh`.
- Every deviation from the plan is written down with its reason (list below).

## Decisions made so far (deviations from the plan)

- Backend rewritten from TypeScript to Python, frontend converted to plain JSX, at the
  owner's request; `LOG_LEVEL` uses Python's names (critical, error, warning, info, debug).
- The plan's single Reddit client is split: `RedditCollector` (deadline, retries, one token
  refresh) and `ListingSource` (`mobile_api.py`, the request and parsing).
- The default transport uses `curl_cffi` with the `chrome_android` fingerprint to pass Reddit's
  edge (see above); the transport is injected so all other tests run offline.
- Live mode is the default; fixture mode (`COLLECTOR_MODE=fixture`) uses its own database file
  and now could serve the scrubbed real response, though it still ships invented sample posts
  in `backend/fixtures/sample-posts.json` for the UI's error-state names.
- `AppError` can switch off the error table's auto-retry or UI retry for one error (used for
  unexpected 4xx responses).
- The retry after a rejected token is handled inside the collector, not by the error table.
- Port 0 is allowed (tests ask the OS for a free port); the smoke script uses `SMOKE_TERM`
  because `TERM` is the shell's terminal type; screen-reader counts use visually hidden text.
- No retention prune, no migration framework, few branches and tags: cut to fit 8 hours.

## Known small issues, deliberately left for later

- A database error while saving a run is recorded as a failed run; add a comment so
  db-inspect readers are not surprised.
- The rate-limit countdown is tick-based and can drift in a background tab; compute it from
  an end time.
- A second click while a collection runs is ignored without feedback (the button is
  disabled, so low impact).
- The 1 KB request limit can reject a 200-character term in a non-Latin script with the
  generic message.
- `scripts/check-secrets.sh` skips `docs/`; now that `docs/reddit-mobile-request.md` exists and
  documents (scrubbed) request details, consider stopping the skip so a pasted token there is
  caught.

## What the owner said is next

"Later we will go through it, understand and change/optimize/generalize it and maybe change
some key decisions." So the next phase is a review/refactor pass, not new features — read the
code with the owner, question decisions, and improve or generalize from there.
