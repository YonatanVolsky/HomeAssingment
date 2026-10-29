# Reddit Search Collector: Workplan

The detailed plan is split by component in [plan/](plan/README.md). This file
keeps the summary, the key decisions, and the completion criteria.

## Brief summary

1. A user enters a term (Appendix A defines the scraping target as posts from a
   subreddit, e.g. r/ubisoft).
2. The backend performs a live Reddit collection.
3. Collection scrapes the **mobile app's** traffic using direct HTTP requests,
   reverse-engineered, in our own implementation.
4. Must not use Reddit's official API or browser automation (Selenium,
   Puppeteer, Playwright).
5. Results are saved in a local database and served by a local backend.
6. The frontend shows post cards with a link to the original Reddit post.
7. Loading, empty and failure states are clear.
8. Submission: source, README with exact setup (no secrets), and a short design
   note with limitations and next steps.
9. Interview: run it live, walk through browser, backend, Reddit and database,
   discuss decisions; reviewers also run it from the README.
10. Eight-hour limit. AI tools are expected. Unfinished parts must be documented.

## Key decisions

- **What "term" means:** primary is a subreddit (`ubisoft`, `r/ubisoft`), sorted
  by New. Free-text search is a stretch goal, only if the mobile search request
  is cheap to capture. Confirm with the reviewers by email early.
- **Stack:** TypeScript, Node 22 LTS (Node 20 is end of life), Fastify, zod, SQLite (`better-sqlite3`),
  undici, React + Vite, Vitest. See the decision table in `plan/README.md`.
- **Data model:** `posts`, `collections` (runs, including failures),
  `collection_posts`. A feed is the post set of a term's latest successful run.
  A failed run never replaces the last good feed.
- **Cache and freshness:** in-memory token cache, 60 s result cache with a
  Refresh override, in-flight de-duplication, stale hint after 10 min, one
  overall collection deadline (25 s). The UI always shows when data was
  collected and whether it was live or cached. Fixture mode uses its own DB
  file so sample data never mixes with real data.
- **Capture environment:** Android Studio emulator (rooted, no Play Store image)
  or a physical Android phone, not MEmu (Windows-only). See `plan/01`.
- **Compliance:** documented endpoint, a mechanical grep check for forbidden
  libraries and hosts, no secrets in the repository.

## Components

| # | File | Budget |
|---|---|---:|
| 00 | [Foundations](plan/00-foundations.md) | 20 min |
| 01 | [Reddit capture](plan/01-reddit-capture.md) | 120 min |
| 02 | [Collector](plan/02-collector.md) | 90 min |
| 03 | [Database](plan/03-database.md) | 35 min |
| 04 | [Backend API](plan/04-backend-api.md) | 45 min |
| 05 | [Frontend](plan/05-frontend.md) | 75 min |
| 06 | [Testing and integration](plan/06-testing-and-integration.md) | 40 min |
| 07 | [Docs and submission](plan/07-docs-and-submission.md) | 50 min |

Total target: **475 minutes (under 8 hours)**. Version control (branches,
commits, merge checklist, tags, secret handling) is in
[plan/README.md](plan/README.md).

## Completion criteria

- A clean machine can follow the README and run the application locally.
- A user can submit a term and receive a live collection.
- The collector uses direct mobile-Reddit HTTP requests and neither the
  official API nor browser automation.
- Results are normalized, persisted in SQLite, and displayed in the feed.
- Duplicate collections do not duplicate posts.
- Loading, empty and failure states are understandable.
- Required post metadata (title, author, comment count, timestamp, link) is
  present.
- Focused automated tests pass.
- Design decisions, limitations and setup requirements are documented.
