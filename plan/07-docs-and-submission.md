# 07 Documentation, interview prep and submission

## Goal and dependencies

Make the project runnable by someone else from the README alone, explain the
decisions honestly, prepare for the interview, and package the submission.
Depends on everything. Written last for accuracy, but outlined early so
decisions get recorded as they are made (keep a running `docs/decisions.md`
scratch list during the work).

## Step-by-step plan

1. **Branch** `docs/submission` from `main`.
2. **README.md** (outline below), written as commands that were actually run.
3. **DESIGN.md** (outline below).
4. **`.env.example` audit**: every variable documented, no secrets.
5. **Clean-machine dry run**: fresh clone into a new directory (ideally a
   different user account, VM or container) and follow the README literally.
   Fix every place the README was wrong or incomplete.
6. **Troubleshooting** section filled with the problems actually hit.
7. **Interview prep** (below).
8. **Packaging** and verification of the archive.
9. Merge, tag `v1.0-submission`.

## Entities

### `README.md` outline

| Section | Content |
|---|---|
| What this is | Two sentences, and a screenshot |
| Requirements | Node 22 LTS (24 also works; `.nvmrc`), npm 10+, a C/C++ toolchain only if the `better-sqlite3` prebuilt binary is unavailable (with the install hint per OS), no database server, no Docker, **no Reddit account, keys or env vars** |
| Quick start | `git clone`, `cd`, `nvm use`, `cp .env.example .env`, `npm install`, `npm run dev`, open `http://localhost:5173` |
| What starts | Backend on `127.0.0.1:3001`, frontend on `5173`, SQLite file at `data/collector.db` created automatically (schema applied on startup) |
| Configuration | Table of every env var, default, meaning (same as 00). States that every `REDDIT_*` value has a working default taken from the app, so nothing is needed to run, and that the anonymous token is fetched at runtime (no secrets in the repo) |
| Using the app | Enter `ubisoft` or `r/ubisoft`; what each state means; Refresh and cache behavior |
| Running tests | `npm test`, `npm run test:live` (opt-in, hits Reddit), `scripts/smoke.sh` |
| Production-like run | `npm run build && npm start` (single process serving the built UI) |
| Offline/fixture mode | `COLLECTOR_MODE=fixture`, when to use it, how the UI labels it, and that it uses its own `data/fixture.db` |
| Inspecting the database | `scripts/db-inspect.sh` or `sqlite3 data/collector.db` examples |
| Re-capturing Reddit traffic | Pointer to `docs/reddit-mobile-request.md` (Android Studio emulator or phone, old APK, sniffer; why not MEmu on macOS). Not needed to run the app |
| Project layout | Short tree with one line per folder |
| Troubleshooting | Port in use, wrong Node version, native module build failure, Reddit 429 or blocked IP, empty results, token errors |
| Limitations and notes | Link to DESIGN.md |

### `DESIGN.md` outline

| Section | Content |
|---|---|
| Overview and request path | The diagram from 04 |
| Decisions | Stack choices (table D1-D9 and the reason for each), SQLite, three-table schema and why a feed is a run, sync request instead of a job queue |
| How the mobile request was found | Emulator, APK version, sniffer, steps, what was required and what was not |
| Compliance | Why this is not the official API and not browser automation, with the exact host and operation, and the compliance script |
| Reliability | Per-request timeouts and one overall collection deadline, retry policy, token handling, in-flight guard, TTL cache, transactional writes, failed runs recorded, fixture data isolated in its own DB |
| Freshness | TTL, stale hint, replace-on-recollect |
| Security | Local-only bind, no secrets committed, log redaction, safe links, no HTML injection, parameterized SQL |
| Known limitations | Subreddit-only (unless search was confirmed and added), no retention prune (the DB grows by one run per live collection), one page (up to `MAX_POSTS`), no pagination, no background refresh, stored counts stale between runs, removed posts disappear only on re-collect, in-flight map is per process, no auth or rate limiting on our own API, dependence on an old app version and unofficial endpoints that can change or be blocked, anonymous token behavior may change |
| What is not finished | Honest list (the brief asks for this explicitly) |
| With more time | Free-text search, retention prune and real migrations, pagination and "load more", scheduled recollection, per-post refresh, richer cards (thumbnail, media type), sort options, observability, container setup, e2e browser test, contract test against live Reddit on a schedule |
| AI usage note | Which tools were used and for what; what was verified by hand |

### Interview preparation

- **Run it live**: two terminals or one `npm run dev`; have `ubisoft` and an
  empty subreddit ready; have the DB inspector open.
- **Walk the path** (one page diagram, also in DESIGN.md):
  browser form, Vite proxy, `POST /api/collections`, validation, cache check,
  token, GraphQL request, parse and normalize, SQLite transaction, read-back,
  JSON response, React state, card render.
- **Be able to explain without notes**: why each required header exists; how the
  token is obtained and refreshed; the parser's required-field policy; why
  feeds are runs rather than a `term` column; what happens on 429; why the
  retry policy treats 401/403 differently; how duplicates are prevented; what
  the cache does and does not guarantee.
- **Expected questions and short answers** (to write in `docs/interview-notes.md`,
  not shipped if it contains opinions about the reviewers):
  - Why mobile instead of web? Brief requirement; app endpoints return
    structured data.
  - Is this the official API? No: explain host, auth and why.
  - What breaks first? App-version-bound request shape and token flow.
  - How would you scale it? Queue, per-term scheduling, shared cache, proxy
    pool, backoff; not needed here.
- **Fallback if Reddit fails during the demo**: fixture mode, clearly stated as
  offline sample data, plus a pre-recorded successful live run (screen capture)
  and the captured HAR scrubbed of tokens.

### Packaging

- Source of truth is the `v1.0-submission` tag.
- Zip: `git archive --format=zip --prefix=reddit-collector/ -o reddit-collector.zip v1.0-submission`.
  This includes tracked files only, so `node_modules`, `data/`, `.env`,
  `captures/` and `*.har` cannot leak.
- Verify the archive: unzip into a new directory, `grep -r` for token-like
  strings, run the README steps once more.
- Included: source, `plan/` (shows the working process), `docs/`, fixtures.
  Whether `plan/` ships is a choice; default is yes since the brief evaluates
  decisions.
- Excluded: `.env`, DB files, raw captures, emulator artifacts.

## Version control plan

- Branch: `docs/submission`.
- Commits, in order:
  1. `docs(readme): add setup, configuration and usage`
  2. `docs: add DESIGN with decisions, limitations and next steps`
  3. `docs(readme): add troubleshooting from dry run`
  4. `docs: add interview notes`
  5. `chore: final dependency and env audit`
  6. `fix(readme): corrections from clean-machine dry run` (as needed)
- Merge criteria: the dry run succeeded with zero manual deviations from the
  README.
- Tag `v1.0-submission`, produce the zip from the tag, re-verify the zip.
- After the tag, only fixes to the README or a blocking bug, each as a new
  commit and a new tag (`v1.0.1`), never moving an existing tag.

## Definition of done

- [ ] A person who has never seen the repo runs it using only the README.
- [ ] README lists versions, env vars, and every command.
- [ ] DESIGN.md states limitations and unfinished parts honestly.
- [ ] Archive contains no secrets, no DB, no captures (verified).
- [ ] Interview checklist rehearsed once, including the fallback demo.
