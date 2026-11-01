# Plan index

One file per component. Each component file has the same four parts:

1. **Goal and dependencies**
2. **Step-by-step plan** (ordered, each step small enough to be one commit)
3. **Entities** (every module, type, table and function, fully specified so its
   behavior can be reviewed or changed before code is written)
4. **Version control plan** (branch, commit sequence, merge criteria)

| # | File | Component | Budget |
|---|---|---|---:|
| 00 | [00-foundations.md](00-foundations.md) | Repo, tooling, config, errors, shared contracts | 20 min |
| 01 | [01-reddit-capture.md](01-reddit-capture.md) | Reverse-engineering the mobile request, fixtures | 120 min |
| 02 | [02-collector.md](02-collector.md) | Reddit client, parser, normalization | 90 min |
| 03 | [03-database.md](03-database.md) | SQLite schema, repository | 35 min |
| 04 | [04-backend-api.md](04-backend-api.md) | HTTP API, collection service, cache, errors | 45 min |
| 05 | [05-frontend.md](05-frontend.md) | Search, feed, states | 75 min |
| 06 | [06-testing-and-integration.md](06-testing-and-integration.md) | Test strategy, smoke test, acceptance | 40 min |
| 07 | [07-docs-and-submission.md](07-docs-and-submission.md) | README, design note, interview, packaging | 50 min |

Total: **475 minutes (7 h 55 min)**, inside the 8-hour hard limit from the brief
(20+120+90+35+45+75+40+50). Budgets are targets, not slack: see "Time-boxing and
fallback" below.

## Brief requirements and where they are covered

| Brief requirement | Covered in |
|---|---|
| Accept a term, start a live collection | 04 (POST /api/collections), 05 (form) |
| Own scraper, mobile app, direct HTTP, no browser automation, no official API | 01, 02 |
| Feed of cards, link to original | 05 |
| Local DB, feed served by local backend | 03, 04 |
| Loading, empty, failure states | 04 (error codes), 05 (state machine) |
| README with exact setup, versions, env vars, no secrets | 07 |
| Design note, limitations, improvements | 07 |
| Interview: run, demo, walk the path, discuss decisions | 07 |

## Open question for the reviewers (send before starting capture)

The brief says a user enters a "term" and sees "matching posts"; Appendix A
describes scraping one subreddit. The plan treats the term as a subreddit name.
Email the reviewers early (the brief invites questions) to confirm:

1. Is a subreddit name an acceptable "term", or is free-text search expected?
2. Is it fine to use the Android Studio emulator or a physical Android phone
   instead of MEmu (MEmu is Windows-only; the brief says "you can", not "must")?

The data model is keyed by `term`, so a later switch to free-text search does not
change the schema. Do not wait for the answer to start the capture.

## Stack decisions (change here first, then in the component files)

> **Changed on 2026-11-01:** FastAPI was replaced by an Express web service (`server/`) in
> front of a Python TCP collector (`backend/app/inner/`); see the top-level README.
>
> **Changed on 2026-10-29:** the backend was rewritten in Python (FastAPI, pydantic, the
> built-in `sqlite3`, httpx, pytest) and the frontend converted to plain React JSX, so the code
> is in the author's language. Behavior, tests and structure are unchanged; module names in the
> component files below still use the TypeScript spelling (`collectionService.ts` is now
> `collection_service.py`). The table below is the original decision, kept for the record;
> the current reasoning is in `DESIGN.md`.

| # | Decision | Choice | Why | Alternative and cost |
|---|---|---|---|---|
| D1 | Language | TypeScript on Node 22 LTS (24 also supported) | One language across frontend, backend, tests. Node 20 reached end of life in April 2026 | Python backend: two toolchains to document |
| D2 | Layout | npm workspaces: `backend/`, `frontend/`, `packages/contracts/` (fallback: one shared `types.ts` if resolution between the two tsconfig modes causes friction) | One `npm install`, one `npm run dev` | Separate repos: more README steps |
| D3 | HTTP server | Fastify | Built-in `inject()` for tests without ports, schema support, pino logging with redaction | Express: more familiar, needs extra test tooling |
| D4 | Validation | zod | Same library validates request bodies and Reddit responses | Hand-written checks: more bugs |
| D5 | Database | SQLite via `better-sqlite3` | Zero services, synchronous API, transactions are trivial | `node:sqlite` has no native build but is still marked experimental on Node 22. Risk with better-sqlite3: native build on a reviewer machine; mitigated by prebuilt binaries for LTS Node versions (hence D1) and a troubleshooting entry |
| D6 | Outbound HTTP | `undici` (`Agent`, `request`) | Keep-alive, per-phase timeouts, mock agent for tests | Built-in `fetch`: fewer timeout controls |
| D7 | Frontend | React + Vite + TypeScript, plain CSS | Fast to demo, no UI framework to explain | None needed |
| D8 | Tests | Vitest (backend and frontend), Testing Library for UI | One runner everywhere | Jest: slower, more config |
| D9 | Dev runner | `tsx watch` for the backend, `concurrently` for `npm run dev` | Reviewers run one command | Two terminals documented |

Node version is pinned in `.nvmrc` (22) and `engines` (`>=22`).

## Build order and dependencies

```
00 foundations
   ├── 01 capture ──► 02 collector ──┐
   └── 03 database ──────────────────┼──► 04 backend ──► 05 frontend ──► 06 integration ──► 07 docs
                                      │
        (04 runs against a fake collector built from the fixtures
         while 01/02 are still in progress)
```

`01` is the riskiest and is started first, but `03` and `04` do not depend on a
working scraper, so they can proceed against fixtures if the capture stalls.

## Time-boxing and fallback

- If there is no replayable request at the **2h mark** of capture: stop, send the
  reviewers a short clarification email (the brief invites this), and continue
  `03`, `04`, `05` using fixtures and the fake collector. A working product with
  an honest "scraper not finished, here is exactly where it stopped" is better
  than nothing.
- If anything else exceeds its budget by 50%, cut scope in this order:
  1. Free-text search (keep subreddit only).
  2. Restoring the last term on page reload.
  3. Stale hint in the UI.
  4. Accessibility and responsive polish beyond the basics.

Already cut from the earlier draft to fit 8 hours: retention prune, numbered
migration files, pre-commit hook, per-component branches and tags.

## Version control plan (applies to the whole project)

### Model

Few branches, many small commits. The history should read as one commit per
numbered step in the component files.

- `main` is always runnable: `npm install && npm test` passes on it.
- The repository already has `Initial commit` on `main`. The first commit on top
  is this plan (branch `docs/plan`), before any code.

| Branch | Components | Merges after |
|---|---|---|
| `docs/plan` | These plan files | this review |
| `docs/capture` | 01 | a documented request replays with plain HTTP, fixtures committed |
| `feat/app` | 00, 02, 03, 04, 05, 06 (commit sequences in each file, in build order) | lint + typecheck + tests pass, acceptance checklist done |
| `docs/submission` | 07 | clean-machine dry run succeeds |

Merge with `git merge --no-ff <branch>` so each branch is one visible merge.
`00` scaffold is the first commits on `feat/app`; `03` and `02` can be committed
in either order.

### Commits

- Conventional Commits: `type(scope): summary`. Types: `feat`, `fix`, `test`,
  `docs`, `chore`, `refactor`. Scopes: `contracts`, `config`, `capture`,
  `collector`, `db`, `api`, `ui`, `scripts`, `readme`.
- One logical step per commit, matching the numbered steps in each component
  file. Tests ship in the same commit as the code they cover.
- Body explains the why when it is not obvious (for example, why a header is
  required). Never paste tokens, cookies or raw captures into messages.
- Commits made with AI assistance carry the `Co-Authored-By` trailer. This is
  consistent with the brief, which asks for AI tools to be used and for the
  decisions to be explained.
- No force-push to `main`. Squash is not used, to keep per-step history visible
  to reviewers.

### Merge checklist (run before every merge to `main`)

1. `npm run lint && npm run typecheck && npm test` pass.
2. `git diff main...HEAD` self-reviewed (or `/code-review`) for leftover debug
   code, tokens and TODOs.
3. `scripts/check-secrets.sh` passes (see below).
4. The definition of done of the components in the branch is ticked.
5. Merge with `git merge --no-ff <branch>`.

### Tags

| Tag | Meaning |
|---|---|
| `v0.2-capture` | 01 merged, request documented |
| `v1.0-submission` | everything merged, dry run done. This is what gets zipped |

### Secrets and sensitive files

- `.gitignore` includes: `node_modules/`, `dist/`, `.env`, `.env.*` except
  `.env.example`, `data/`, `*.db`, `*.db-wal`, `*.db-shm`, `captures/`, `*.har`,
  `coverage/`, `.DS_Store`.
- Raw captures (HAR, sniffer exports) live only in `captures/` (ignored).
  Only scrubbed fixtures under `backend/test/fixtures/` are committed, produced
  by `scripts/scrub-fixture.mjs`.
- `scripts/check-secrets.sh` is run by hand in the merge checklist and before
  zipping. It scans tracked and staged files for **token-shaped values**, not
  for words: JWT-like strings (`eyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{10,}`),
  `Bearer ` followed by 20 or more token characters, and quoted values of
  `client_secret`, `access_token`, `refresh_token`, `loid`, `device_id` longer
  than 16 characters. It excludes `plan/`, `docs/`, itself and fixtures that
  contain the literal `REDACTED`. Code that builds an `Authorization` header from
  a variable does not match. It prints file and pattern, never the matched value.
  There is no git hook (cut for time).
- Nothing is pushed anywhere unless the owner asks. A remote, if any, is a
  private repository. Submission is a `git archive` zip of the `v1.0-submission`
  tag (see 07).

### Recovery

- Capture work is experimental: do it on `docs/capture` and keep dead ends in
  commit history, not in `main`.
- If a merge breaks `main`, revert the merge commit (`git revert -m 1 <sha>`),
  not the individual commits.
