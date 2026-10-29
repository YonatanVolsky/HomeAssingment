# Handoff: continue on another computer

Written 2026-10-29 at the end of the first working session. A new Claude Code session should
read this file first; it replaces the conversation history, which stays on the old machine.

## Where things stand

- **Work branch: `feat/python`** (contains everything; built on `feat/app`). Nothing is merged
  into `main` beyond the plan, on purpose: the merge waits for the live Reddit part.
- **Done and tested:** Python backend (FastAPI, sqlite3, httpx; 233 pytest tests), React JSX
  frontend (88 Vitest tests), scripts (smoke, compliance, secrets, db-inspect), README,
  DESIGN.md, docs/acceptance.md. The full flow works in fixture mode
  (`COLLECTOR_MODE=fixture npm run dev`).
- **Not done:** the Reddit mobile request. `backend/app/collector/reddit/mobile_api.py` is a
  placeholder that answers "Live Reddit collection is not available yet". Everything around
  it (token cache, retries, deadline, error mapping, storage, API, UI) is built.
- `feat/app` is the earlier TypeScript version, kept for history only.

## Set up the new computer

```bash
git clone https://github.com/YonatanVolsky/HomeAssingment.git
cd HomeAssingment
git checkout feat/python
```

Then follow README.md "Setup (once)": Python 3.11+ and Node 22+ are needed. Check it works:

```bash
npm test                               # expect: backend 233 passed, frontend 88 passed
COLLECTOR_MODE=fixture npm run dev     # open http://localhost:5173, search "ubisoft"
```

On Windows, use the Windows commands in README.md and run backend and frontend in two
terminals. Free disk space: the emulator needs about 15-20 GB.

## Next step: the Reddit capture (needs a person)

Goal: record the HTTP traffic of the Reddit Android app while it shows r/ubisoft sorted by
New, so the scraper can replay those requests. Full background: `plan/01-reddit-capture.md`.

1. **Emulator.** In Android Studio: Device Manager → create a device → system image
   **Android 13 (API 33), "Google APIs"** (not "Google Play", which cannot be rooted). Pick
   arm64 on Apple Silicon, x86_64 on Intel/AMD. On Windows, MEmu (the brief's suggestion)
   also works. Start it, then run `adb root` (adb is in Android Studio's `platform-tools`).
2. **Reddit app.** Download a Reddit APK **older than 2024.44** for the emulator's
   architecture (for example from APKMirror) and install it: `adb install reddit.apk`.
   Note the exact version.
3. **Proxy.** Install HTTP Toolkit → "Android device via ADB". It installs its certificate
   on the rooted emulator and starts intercepting.
4. **Record.** In the app, logged out: open r/ubisoft, sort by **New**, scroll twice. Then
   search for something inside r/ubisoft once. Also open a subreddit that does not exist.
5. **Export.** In HTTP Toolkit, export everything as a **HAR file** into the repo's
   `captures/` folder (git ignores it; it contains tokens and must never be committed).
6. **If the app shows network errors while intercepting**, it is probably certificate
   pinning: stop and ask Claude to walk through HTTP Toolkit's Frida option.

## Prompt to start the new Claude session

> Read docs/HANDOFF.md, WORKPLAN.md and plan/01-reddit-capture.md. We are on branch
> feat/python. The capture HAR is in captures/. Continue: find the token and listing
> requests, replay them with curl and Python, document them in
> docs/reddit-mobile-request.md, and implement the real request and parser in
> backend/app/collector/reddit/mobile_api.py test-first, as the plan says.

## What the next session does after the capture

1. Identify the anonymous token request and the subreddit listing request in the HAR; replay
   both with curl, then with Python httpx (if Python is blocked but curl works, try
   `curl_cffi`); find the minimal headers by removing them one at a time.
2. Write `docs/reddit-mobile-request.md` (template in plan/01) and `scripts/scrub-fixture.py`
   (removes tokens, cookies, device ids) to save real responses as test fixtures.
3. Implement, test-first: the token fetcher and the listing source in `mobile_api.py`, a
   pydantic schema for the raw response, `parse_listing` using the helpers in
   `app/collector/mappers.py`. Set `LIVE_COLLECTION_AVAILABLE = True`.
4. Add the app's Reddit hosts to the allow-list in `scripts/check-compliance.sh`.
5. Add one test marked `live` (`npm run test:live`), run the acceptance checklist against
   live Reddit (docs/acceptance.md), look at the UI in a browser, merge `feat/python` into
   `main`, write `docs/interview-notes.md`, then tag `v1.0-submission` and zip it (plan/07).

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
  refresh) and `ListingSource` (request and parsing, written after the capture).
- Live mode stays the default even before the capture; it warns at startup and its error
  offers no retry. Fixture mode uses its own database file.
- Fixture mode serves invented sample posts (`backend/fixtures/sample-posts.json`); switch to
  scrubbed real responses after the capture.
- `AppError` can switch off the error table's auto-retry or UI retry for one error (used for
  unexpected 4xx responses and the placeholder).
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
- `scripts/check-secrets.sh` skips `docs/`; stop skipping it once
  `docs/reddit-mobile-request.md` exists, so a pasted token there is caught.

## Time used

Not measured precisely. By the plan's budgets, what remains is the capture (120 minutes) plus
the live integration, final docs and packaging (about 60 minutes); the brief's limit is 8 hours
in total.
