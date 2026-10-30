# Reddit mobile app request spec

How the Reddit Android app lists a subreddit's posts, captured by reverse-engineering its
traffic. This is the app's own internal traffic, not the official developer API and not a
browser.

## Capture setup

| Item | Value |
|---|---|
| App | Reddit for Android **2024.24.0** (build 1675730), from APKMirror |
| Device | Android 13 (API 33) emulator, arm64, `sdk_gphone64_arm64` |
| Proxy | mitmproxy 12.3.1, its CA installed as a system certificate on the rooted emulator |
| Account | Logged out (anonymous) |
| Actions | Opened r/ubisoft, scrolled; opened a post; searched inside the subreddit |

No certificate pinning was encountered: once mitmproxy's CA was a system certificate, all
traffic decrypted. Raw capture files live only in `captures/` (git-ignored); they contain
anonymous session tokens and are never committed.

## Hosts used

| Host | Purpose |
|---|---|
| `www.reddit.com` | Anonymous OAuth token |
| `gql-fed.reddit.com` | GraphQL API: subreddit feed, search, subreddit info |
| `oauth.reddit.com` | Seen for some calls; not needed for the listing |
| media hosts (`i.redd.it`, `*.thumbs.redditmedia.com`, `styles.redditmedia.com`) | Images, not needed |

## Token request

```
POST https://www.reddit.com/auth/v2/oauth/access-token/loid
Content-Type: application/json; charset=UTF-8
Authorization: Basic <app client id>     (26-char header; the public client id built into the app)
User-Agent: Reddit/Version 2024.24.0/Build 1675730/Android 13

body: {"scopes":["*","email","pii"]}
```

Response (JSON):

| Field | Meaning |
|---|---|
| `access_token` | Bearer token for the GraphQL calls |
| `expires_in` | Lifetime in seconds (observed **86399**, ~24 h) |
| `expiry_ts`, `scope`, `token_type` | Expiry timestamp, granted scopes, `"bearer"` |

The `Authorization` on this request is HTTP Basic with the app's **client id and no secret**
(a public identifier shipped in every copy of the app, the same role as the client id in the
official API's installed-app flow). The response token is anonymous: no user is logged in.
`TokenProvider` (`app/collector/token_provider.py`) caches it until 60 s before `expires_in`.

## Listing request (subreddit feed)

```
POST https://gql-fed.reddit.com/
Authorization: Bearer <access_token>
Content-Type: application/json; charset=utf-8
User-Agent: Reddit/Version 2024.24.0/Build 1675730/Android 13
x-apollo-operation-name: SubredditFeedElements
Accept: multipart/mixed; deferSpec=20220824, application/json
```

Body (a persisted GraphQL query, sent as a hash, not the query text):

```json
{
  "operationName": "SubredditFeedElements",
  "variables": { "subredditName": "ubisoft", "sort": "NEW", "optedIn": true,
                 "includePostStats": true, "includeAwards": true,
                 "includeStillMediaAltText": true, "includeCurrentUserAwards": false,
                 "includeSubredditInPosts": false, "includeMediaAuth": false,
                 "adContext": {...}, "feedContext": {...}, "feedFilters": {}, "forceAds": {} },
  "extensions": { "persistedQuery": { "version": 1,
                  "sha256Hash": "5f8ce513df609c3b3da05d797dbff3fa042f7761380747ee486e20e6f2aafccb" } }
}
```

| Variable | Use |
|---|---|
| `subredditName` | The subreddit (our "term"), lowercase |
| `sort` | `NEW`, `HOT`, `TOP`, `RISING`. We send `NEW` |
| `adContext`, `forceAds` | Ad targeting; ads come back as `AdPost` nodes we skip |
| the `include*` flags | Which optional fields the response embeds |

The captured app used `sort: HOT`; `NEW` is the same request with the variable changed.
Pagination: the response's `pageInfo.endCursor` feeds an `after` variable for the next page
(not used; we fetch one page up to `MAX_POSTS`).

## Response map

Path to the post list: `data.postFeed.elements.edges[].node`. Subreddit name is
`data.postFeed.prefixedName` (`"r/ubisoft"`).

| Post field | JSON path | Notes |
|---|---|---|
| `id` | `node.id` | e.g. `t3_1wcg6wx` |
| `title` | `node.title` | |
| `author` | `node.authorInfo.name` | `DeletedRedditor`/`[deleted]` → null |
| `commentCount` | `node.commentCount` | |
| `score` | `node.score` | |
| `createdAt` | `node.createdAt` | ISO like `2026-09-10T11:14:02.764000+0000` → ISO UTC |
| `permalink` | `node.permalink` | relative `/r/...` → absolute `https://www.reddit.com/...` |
| `previewText` | `node.content.markdown` | null for link posts; truncated to 300 chars |
| `flair` | `node.flair.text` | null when absent |
| `subreddit` | `data.postFeed.prefixedName` | without `r/` |

Node types seen: `SubredditPost` (real posts) and `AdPost` (ads, **skipped**). `isStickied`
marks pinned posts; they are kept. Parsing is implemented and tested in
`app/collector/reddit/parse_listing.py` against a scrubbed real response
(`backend/tests/fixtures/listing-new-ok.json`).

## Errors and limits

| Signal | Meaning |
|---|---|
| HTTP 401/403 on GraphQL with a valid body | Token expired, or the request was blocked (see below) |
| `x-ratelimit-remaining`, `x-ratelimit-reset` (seconds) | Rate-limit budget; `reset` feeds our `Retry-After` |
| Observed limits | `x-ratelimit-used: 148`, `remaining: 452`, `reset: 283` (per ~600/10 min window) |
| Not-found subreddit | Not captured (the app did not fire a feed request for a bad name). Handle as an empty/`NOT_FOUND` result; confirm when live |

## Transport fingerprint (resolved)

Replaying the request from a default Python HTTP client (`httpx`) returns **HTTP 403** with
Reddit's HTML block page from the edge (Varnish), *before* the token is checked. The token and
body are correct; Reddit's edge distinguishes a default client from a real app by the
TLS/HTTP-2 client fingerprint (the app uses OkHttp over HTTP/2).

The fix is to connect the way the app does. The collector's default transport
(`app/collector/reddit/mobile_api.py`, `CurlCffiTransport`) uses **`curl_cffi`** with the
`chrome_android` profile, which presents a real Android-client TLS/HTTP-2 fingerprint. The
request stays a direct HTTP request we build ourselves (no browser, no automation); only the
transport-layer handshake is matched to a real mobile client. A default client's fingerprint
is the one thing Reddit's edge rejects.

Verified live on 2026-10-30: `pytest -m live` fetched 10 newest posts of r/ubisoft. Why not
OkHttp exactly: `curl_cffi` 0.17 has no OkHttp profile, and `chrome_android` is accepted, so a
real Android-client fingerprint — not OkHttp specifically — is what the edge checks for.

## Compliance note

This replays the **mobile app's own** requests: its public client id, its anonymous token
flow, and its internal GraphQL endpoint (`gql-fed.reddit.com`) with a persisted-query hash. It
is not the official developer API (no registered developer app, no `*.json` public endpoints,
no PRAW/snoowrap), and no browser or automation drives the app. `scripts/check-compliance.sh`
enforces this and allows the Reddit hosts named above with a pointer to this file.
