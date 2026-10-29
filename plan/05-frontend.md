# 05 Frontend

## Goal and dependencies

A small React single-page app: enter a subreddit term, start a collection, see a
feed of cards, and always understand what state the system is in. Depends on
`00` (contracts) and the `04` API shape (it can be built against a mock server or
the fixture-mode backend).

## Step-by-step plan

1. Work on `feat/app`.
2. **Scaffold** Vite + React + TS in `frontend/`, proxy `/api` to
   `http://127.0.0.1:3001`.
3. **API client** (`api/client.ts`) with typed functions, `AbortController`, and
   error normalization to `ErrorResponse`. Tests with mocked `fetch`.
4. **Formatting utilities** (`lib/format.ts`): relative time, counts, safe link
   check. Tests first.
5. **State machine** `useCollection` reducer. Tests for every transition.
6. **`PostCard`** and **`PostList`** with tests.
7. **State components**: `LoadingState`, `EmptyState`, `ErrorBanner`,
   `FreshnessBar`.
8. **`SearchForm`**: input, Collect button, Refresh button.
9. **`App`** composition; periodic tick (every 15 s) to update relative times.
10. **Accessibility pass**: labels, focus order, `aria-live`, keyboard use.
11. **Responsive pass**: single column on mobile, readable max width on desktop.
12. **Optional**: restore the last term on load via `GET /api/posts`
    (`localStorage` wrapped in try/catch).
13. **Manual state check** (list below).

## Entities

### State machine (`useCollection`)

State shape:

```ts
type View =
  | { kind: 'idle' }
  | { kind: 'loading'; term: string; previous?: CollectionResponse }
  | { kind: 'success'; data: CollectionResponse }
  | { kind: 'empty'; data: CollectionResponse }            // success with 0 posts
  | { kind: 'error'; error: ErrorResponse['error']; term: string; lastGood?: CollectionResponse }
```

| From | Event | To |
|---|---|---|
| any | `submit(term, force)` | `loading` (keeps `previous` so the old feed stays visible, dimmed) |
| `loading` | response, `posts.length > 0` | `success` |
| `loading` | response, `posts.length === 0` | `empty` |
| `loading` | error response or network failure | `error` (with `lastGood` from the response or `previous`) |
| `error` | `retry` (only when `error.retryable`, and after any `retryAfterSeconds`) | `loading` with the same term and `force: false` |
| any | `submit` while `loading` | ignored (button is disabled, and the reducer guards it) |

Network failures (backend down, request aborted after 35 s) become a synthetic
error with code `NETWORK`, `retryable: true`, and message "Cannot reach the
local server. Is the backend running?". The 35 s client timeout is the
collector's 25 s `COLLECTION_DEADLINE_MS` plus 10 s for the database write and
response (see 02), so the backend always answers first.

### Components

| Component | Props | Behavior |
|---|---|---|
| `App` | none | Holds `useCollection`; renders the form, `FreshnessBar`, and the view for the current state |
| `SearchForm` | `onSubmit(term, force)`, `loading`, `hasResult` | Label "Subreddit", placeholder `r/ubisoft`. Submit on Enter. Button "Collect posts" disabled and `aria-busy` while loading. "Refresh" button (sends `force: true`) is shown only when a result exists. Trims input and blocks blank submission with an inline message, before any request |
| `FreshnessBar` | `collection`, `now`, `staleAfterSeconds`, `collectorMode` | "Collected 20 s ago", a `live` or `cached` badge from `source`, "stale, refresh" hint when older than `staleAfterSeconds`, and an "Offline sample data" banner when `collectorMode === 'fixture'` |
| `LoadingState` | `term` | Spinner and text "Collecting posts from r/{term}… this can take up to ~25 s". Wrapped in `role="status"` |
| `EmptyState` | `term` | "No posts found in r/{term}." plus guidance: check the spelling, try another subreddit, the subreddit may be new or private |
| `ErrorBanner` | `error`, `onRetry`, `lastGood` | Message from the API. The "Try again" button is shown only when `error.retryable` is true (the UI never keeps its own list of codes); when `retryAfterSeconds` is present (`RATE_LIMITED`) the button is disabled with a visible countdown until it elapses. When `retryable` is false (invalid term, unknown subreddit) there is no button and the message tells the user to change the input. "Showing results from {time}" when `lastGood` is rendered below. `role="alert"` |
| `PostList` | `posts` | `<ul>` of `PostCard`, newest first as returned |
| `PostCard` | `post` | See below |

### `PostCard` content

| Element | Source | Notes |
|---|---|---|
| Title | `title` | Heading level 3; plain text (React escapes), line clamp 3 |
| Flair badge | `flair` | Hidden if null |
| Meta line | `author`, `subreddit`, `createdAt` | `u/name` or "[deleted]"; `r/sub`; relative time with the full ISO time in a `title`/`<time dateTime>` |
| Preview | `previewText` | Hidden if null; max 3 lines |
| Stats | `commentCount`, `score` | Icons are decorative (`aria-hidden`) with text labels for screen readers, e.g. "14 comments" |
| Link | `permalink` | "Open on Reddit", `target="_blank"`, `rel="noopener noreferrer"`. Rendered only if `isSafeRedditUrl(permalink)`; otherwise the link is omitted |

### Utilities (`lib/format.ts`)

| Function | Behavior |
|---|---|
| `relativeTime(iso, now)` | "just now", "49 min ago", "3 h ago", "2 d ago", falls back to a date after 30 days. Pure, `now` injected |
| `formatCount(n)` | `1234` to `1.2k`, exact below 1000 |
| `isSafeRedditUrl(url)` | `https:` and hostname `reddit.com` or `*.reddit.com` only |

### API client (`api/client.ts`)

| Function | Behavior |
|---|---|
| `collect(term, force, signal)` | `POST /api/collections`, returns `CollectionResponse` or throws a typed `ApiError` carrying `ErrorResponse['error']` and `lastGood` |
| `getPosts(term, signal)` | `GET /api/posts?term=` |
| `getHealth()` | `GET /api/health`, called once on load; on failure the app assumes defaults (`staleAfterSeconds = 600`, `live`) |

The frontend never calls Reddit and never receives tokens or headers.

### UI states checklist (for manual verification)

1. Idle: only the form, with an example hint.
2. Loading: spinner, button disabled, previous feed dimmed if any.
3. Success live, success cached, with the correct badge.
4. Empty: zero posts message with guidance.
5. Error `INVALID_TERM`: inline and from the server for `r/`, `r/a` or names
   with invalid characters (`bad name!`).
6. Error `RATE_LIMITED`: countdown hint, Retry disabled until elapsed.
   Error `NOT_FOUND_SUBREDDIT`: no Retry button, message asks to change the input.
7. Error with `lastGood`: error banner and the old feed with its timestamp.
8. Backend down: `NETWORK` error.
9. Stale hint after the threshold (set `STALE_AFTER_SECONDS=10` temporarily).
10. Keyboard only: tab order, Enter to submit, visible focus ring.
11. 375 px width: no horizontal scroll.

## Version control plan

- Branch: `feat/app`.
- Commits, in order:
  1. `feat(ui): scaffold vite react app with api proxy`
  2. `feat(ui): add api client with typed errors`
  3. `feat(ui): add formatting utilities`
  4. `feat(ui): add collection state machine`
  5. `feat(ui): add PostCard and PostList`
  6. `feat(ui): add loading, empty, error and freshness components`
  7. `feat(ui): add search form and compose app`
  8. `feat(ui): accessibility and responsive pass`
  9. `feat(ui): restore last term on load` (optional)
- Done when: component and reducer tests pass; manual states 1-11 checked;
  screenshots (without tokens, there are none to leak) are optional for the
  design note and are stored under `docs/screenshots/`.

## Definition of done

- [ ] Every state in the machine is reachable and verified by a test.
- [ ] No external link renders without `isSafeRedditUrl` passing.
- [ ] Double-click on Collect sends one request.
- [ ] Works at 375 px and 1280 px, keyboard-only usable.
- [ ] No `dangerouslySetInnerHTML` anywhere (checked with grep).
