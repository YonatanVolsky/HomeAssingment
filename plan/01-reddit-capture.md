# 01 Reddit capture (reverse-engineering the mobile request)

## Goal and dependencies

Find the exact requests the Reddit mobile app makes to list posts of a
subreddit sorted by New, and prove they can be replayed with plain HTTP and no
app, browser, or official API. Output is a spec document and scrubbed fixtures
that `02-collector` is built from. Depends on `00`. Highest risk, so it starts
first and is time-boxed (see the fallback in the index).

## Compliance rules (re-read before starting)

- Replay what the **mobile app** sends. Direct HTTP only.
- No Selenium, Puppeteer, Playwright, or any browser automation, including for
  getting tokens.
- No official API: no registered developer app, no `*.json` public endpoints,
  no `oauth.reddit.com` REST with a developer client id, no PRAW.
- Document exactly which host/path/operation is used and why it is the app's
  internal traffic. This is an expected interview question.
- Raw captures never get committed.

## Step-by-step plan

1. **Branch** `docs/capture`.
2. **Environment** (30 min budget). MEmu (suggested in the brief) is
   Windows-only and this machine is a Mac, so use one of:
   - **Android Studio emulator** (preferred): create an AVD from a "Google APIs"
     system image (not "Google Play", which cannot be rooted). On Apple Silicon
     pick an arm64 image; on Intel pick x86_64. Start it, then `adb root`.
   - **Physical Android phone** with USB debugging, if one is available and rooted.

   Then:
   - Install a Reddit APK **older than 2024.44** with `adb install` (pick the
     APK variant that matches the emulator architecture). Record the version.
   - Install HTTP Toolkit (or mitmproxy) and use its "Android device via ADB"
     option. On a rooted device it injects its CA into the system store; Android
     7+ ignores user-installed CAs, so a user CA alone is not enough. Android 14+
     keeps system CAs in an APEX module, so prefer an Android 13 (API 33) image.
   - If the app still refuses connections (certificate pinning), use the
     sniffer's Frida pinning-bypass script before anything else.
3. **First capture** (20 min): launch the app logged out, open r/ubisoft, sort
   by New, scroll twice. Export a HAR into `captures/` (ignored).
4. **Identify** (20 min): list the hosts and endpoints; find the request whose
   response contains post titles. Note method, path, query, headers, body.
5. **Token flow** (20 min): find how the app gets its first anonymous token (a
   request before the listing). Record: endpoint, client id and where it comes
   from, device id generation, token lifetime, refresh behavior.
6. **Minimal replay** (30 min): reproduce the token request and the listing
   request with `curl`. Remove headers one at a time until it breaks, to find
   the required set. Record the minimal set.
6b. **Replay from Node** (10 min): send the same two requests from a throwaway
   Node script using undici. Reddit may treat clients differently by TLS
   fingerprint, header order or User-Agent, so a request that works with `curl`
   can still be blocked from Node. If undici is blocked and curl is not, record
   the difference and try matching header order and User-Agent first. This
   must pass before 02 starts, because 02 uses undici.
7. **Parameters** (10 min): find the variable for subreddit name, sort (New),
   page size, and pagination cursor. Confirm page size limits.
8. **Edge responses** (15 min): capture or provoke an empty subreddit, a
   nonexistent subreddit, a private/banned subreddit, a post with a deleted
   author, an expired token, and a rate-limit (only if it happens naturally;
   do not hammer Reddit).
9. **Write the spec** `docs/reddit-mobile-request.md` using the template below.
10. **Scrub and commit fixtures** with `scripts/scrub-fixture.mjs` (removes
    tokens, device ids, cookies, user identifiers not already public, and trims
    each listing to about 5 representative posts).
11. **Decide config**: which values become `REDDIT_*` env variables (for
    example user agent, app client id) versus constants, and update
    `.env.example` and the config table in 00. Every value gets a working
    default in code, so reviewers run the app with no Reddit setup at all. A
    client id embedded in the app is a public identifier, not a secret: keep it
    as a default and document where it came from in the spec. Anything that is
    truly per-user (a logged-in session) is not used.
12. **Free-text search check** (10 min, during step 4, not at the end): while
    the sniffer is running, also run one search in the app and note whether the
    search request has the same shape as the listing (same host, token, and a
    different operation). Record the answer in the spec. Implement it only if
    the reviewers ask for free-text search or it is near-identical; otherwise
    it is a documented limitation.
13. Merge and tag `v0.2-capture`.

## Entities

### Spec document: `docs/reddit-mobile-request.md`

Template (every field must be filled or marked "not required" with evidence):

| Section | Content |
|---|---|
| App version | APK version used, device model string, emulator or device and Android version |
| Token request | Host, method, path, required headers, body, response fields, lifetime in seconds, how `expiresAt` is derived |
| Listing request | Host, method, path, required headers (minimal set), body or operation name and persisted-query hash if GraphQL, variables: `subredditName`, `sort`, `first` (page size), `after` (cursor) |
| Response map | JSON path to the post list, and per-field paths: id, title, author, comment count, score, created time and its unit/format, permalink, subreddit, flair, body/preview text, stickied/promoted markers |
| Edge shapes | Empty list, unknown subreddit, banned/private, deleted author, removed post, promoted/ad nodes (to be filtered out) |
| Errors | Status codes and bodies for 401/403 (expired token), 404, 429 (and `Retry-After`/rate-limit headers), 5xx |
| Rotating values | Anything that changes per request (request id, session) and how the replay generates it |
| Compliance note | Why this is mobile-app traffic and not the official API. If the app uses a host that is also used by the official API (for example the OAuth token endpoint or `oauth.reddit.com`), state that the credentials and operations are the app's own, not a registered developer app, and add the allow-list entry for `check-compliance.sh` (06) |
| Client fingerprint | Whether curl and undici both work; any header order or User-Agent requirement |
| Limits observed | Max page size, observed rate limits |
| Re-capture guide | Short steps for someone else to redo the capture (no secrets) |

### Fixtures (`backend/test/fixtures/`)

| File | Purpose |
|---|---|
| `token-ok.json` | Token response shape (token value replaced by a placeholder) |
| `listing-new-ok.json` | Normal listing, about 5 posts, includes flair and text posts |
| `listing-empty.json` | Valid subreddit with zero posts |
| `listing-deleted-author.json` | Deleted or anonymous author |
| `listing-with-promoted.json` | Contains an ad or non-post node that must be skipped (if observed) |
| `listing-malformed.json` | Valid JSON with a missing required field, for contract-error tests |
| `error-401.json`, `error-429.json`, `error-5xx.json` | Error bodies and headers (headers kept in a sidecar `*.meta.json`) |
| `subreddit-not-found.json` | Unknown or banned subreddit |

Scrubber behavior (`scripts/scrub-fixture.mjs`): reads a file path argument,
replaces values of keys matching a deny-list (`token`, `access_token`,
`authorization`, `cookie`, `device_id`, `session`, `loid`, `email`) with
`"REDACTED"`, truncates arrays under the post-list path to N items, writes to
`backend/test/fixtures/`. Prints which keys were redacted, never the values.

## Version control plan

- Branch: `docs/capture` (experimental, dead ends allowed in history).
- Commits, in order:
  1. `docs(capture): add spec template and capture environment notes`
  2. `docs(capture): document token flow`
  3. `docs(capture): document listing request and minimal required headers`
  4. `chore(scripts): add fixture scrubber`
  5. `test(capture): add scrubbed fixtures`
  6. `docs(capture): document edge shapes, errors, limits and compliance note`
  7. `chore(config): add REDDIT_* variables found during capture`
- Never committed: HAR files, screenshots with tokens, emulator images.
  `check-secrets.sh` must pass on every commit here.
- Merge criteria: someone can read the spec and issue a successful listing with
  `curl` using only placeholders for tokens; fixtures contain no secrets.
- Tag: `v0.2-capture`.

## Definition of done

- [ ] Token request and listing request replay with plain HTTP, no app running,
      from both `curl` and a Node undici script.
- [ ] Every `REDDIT_*` value has a working default; no setup needed to run.
- [ ] Minimal required header set is documented and verified by removal tests.
- [ ] Response map covers title, author, comment count, timestamp, permalink.
- [ ] Edge and error shapes are captured or explicitly marked "not reproducible".
- [ ] Fixtures are scrubbed and committed; no secrets in history.
- [ ] Compliance note written.

## Risks and mitigations

| Risk | Mitigation |
|---|---|
| MEmu not available on macOS | Android Studio emulator with a rootable Google APIs image, or a physical phone; ask reviewers if they require MEmu |
| App pins certificates | Frida pinning bypass; try an older APK; time-box 45 min then escalate |
| Requests work from curl but are blocked from Node (TLS fingerprint, header order) | Step 6b catches it early; match headers and User-Agent; last resort: document and ask reviewers |
| Token requires values hard to derive (attestation) | Ask reviewers for direction (explicitly invited); document findings |
| Reddit rate limits or blocks the IP while experimenting | Low request rate, reuse tokens, pause between experiments |
| Response format differs by app version | Pin and document the APK version in the spec |
