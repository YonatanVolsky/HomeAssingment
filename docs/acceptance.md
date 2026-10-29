# Acceptance run

Checklist from `plan/06-testing-and-integration.md`. Updated each time it is run.

## Run 1: 2026-10-29, offline (fixture mode)

Environment: macOS 14.6.1 (Apple Silicon), Node 24.12.0, npm 11.6.2, SQLite CLI 3.43.2.
Packages: fastify 5.12.7, better-sqlite3 12.11.1, undici 7.30.1, zod 4.6.7, react 19.3.1, vite 6.4.5.

The live Reddit collector is not wired up yet (it waits for the traffic capture,
`plan/01`), so this run used `COLLECTOR_MODE=fixture`. The UI was checked through
automated component tests, not in a real browser.

| # | Check | Result | How |
|---|---|---|---|
| 1 | Fresh clone, follow README, app starts | Partly | `npm install`, `npm run dev`, `npm run build && npm start` all run on this machine. A clean-machine dry run is still to do (plan/07) |
| 2 | Search `ubisoft`: loading, then a feed of cards | Pass (fixture) | `App.test.tsx`; `scripts/smoke.sh` returned 7 posts |
| 3 | Open a card's link: the correct post opens in a new tab | Pass (unit) | `PostCard.test.tsx` checks `href`, `target`, `rel`. Real Reddit links need live mode |
| 4 | Inspect the DB: posts and one collection row | Pass | `scripts/db-inspect.sh` on a seeded database |
| 5 | Reload restores the term: same feed, Cached badge | Pass (unit) | `App.test.tsx` restore test; `server.test.ts` restart test |
| 6 | Repeat within 60 s is cached; Refresh is live; no duplicate posts | Pass | `smoke.sh`; `persistence.test.ts` (2 runs, posts not duplicated) |
| 7 | Empty subreddit: empty state with guidance | Pass (fixture) | Term `empty`; `App.test.tsx` |
| 8 | `r/a`, `bad name!`, blank: validation message; unknown name: not found, no Retry | Pass | `normalizeTerm.test.ts`, `app.test.ts`, `SearchForm.test.tsx`; fixture term `notfound` |
| 9 | Backend stopped: network error state | Pass (unit) | `client.test.ts`, `App.test.tsx`; `smoke.sh` exits 1 when the backend is down |
| 10 | Simulated failure: error banner, previous feed still shown | Pass | Fixture terms `broken`, `timeout`, `ratelimited` (HTTP 429, `Retry-After: 30`); `persistence.test.ts` |
| 11 | Full test suite green | Pass | `npm test`: backend 248, frontend 88 |

Static checks: `scripts/check-compliance.sh` OK, `scripts/check-secrets.sh` OK, `npm run lint` and
`npm run typecheck` clean.

### Still to do

- Run 2 against live Reddit once the capture is done: rows 2, 3, 6 and 10 with real data, and
  `npm run test:live`.
- Look at the UI in a browser at 375 px and 1280 px, keyboard only, in light and dark mode.
- Clean-machine dry run of the README.
