# Reddit mobile app request spec

How the Reddit Android app lists a subreddit's posts, captured by reverse-engineering its
traffic. This is the app's own internal traffic, not the official developer API and not a
browser.

Implemented in `app/collector/reddit/mobile_api.py`. The transport replays the app's captured
TLS/HTTP-2 fingerprint; see [Transport fingerprint](#transport-fingerprint) for why and how.

## Capture setup

| Item | Value |
|---|---|
| App | Reddit for Android **2024.24.0** (build 1675730), from APKMirror |
| Device | Android 13 (API 33) emulator, arm64, `sdk_gphone64_arm64` (AVD `reddit-capture`) |
| Proxy | mitmproxy 12.3.1, its CA installed as a **system** certificate on the rooted emulator |
| Account | Logged out (anonymous) |
| Actions | Opened the home feed and a subreddit feed, scrolled; opened a post |
| Date | 2026-11-16 |

No certificate pinning was encountered: once mitmproxy's CA was a system certificate, all
traffic decrypted. The CA install is a tmpfs overlay on `/system/etc/security/cacerts`
(`install_ca.sh`) and is lost on every cold boot, so it is re-run after each emulator boot.
Raw capture files (`*.flows`, `akamai_fp.jsonl`, `request.json`) are git-ignored; they contain
anonymous session tokens and are never committed.

**Capture gotcha (networking):** on some boots the emulator's virtual Wi-Fi comes up with an
IPv6 route but no IPv4 route. Reddit's API hosts (`www.reddit.com`, `gql-fed.reddit.com`) are
IPv4-only, so the feed silently fails to load while images (which have IPv6 addresses) still
appear from cache. The failure happens inside the emulator, before any request reaches the
proxy, so nothing shows in mitmproxy. Fix: disable the emulator's Wi-Fi (`adb shell svc wifi
disable`) so Android uses its mobile-data connection, which has IPv4.

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
authorization: Basic <app client id>     (the public client id built into the app)
user-agent: Reddit/Version 2024.24.0/Build 1675730/Android 13
content-type: application/json; charset=UTF-8
accept-encoding: gzip
client-vendor-id: <random UUID>

body: {"scopes":["*","email","pii"]}
```

Response (JSON):

| Field | Meaning |
|---|---|
| `access_token` | Bearer token for the GraphQL calls |
| `expires_in` | Lifetime in seconds (observed **86399**, ~24 h) |
| `expiry_ts`, `scope`, `token_type` | Expiry timestamp, granted scopes, `"bearer"` |

The `authorization` on this request is HTTP Basic with the app's **client id and no secret**
(a public identifier shipped in every copy of the app, the same role as the client id in the
official API's installed-app flow). The response token is anonymous: no user is logged in.
`TokenProvider` (`app/collector/token_provider.py`) caches it until 60 s before `expires_in`.

Header names are lowercase and in the order above, matching the app's capture. See
[Transport fingerprint](#transport-fingerprint) for why order and casing matter.

## Listing request (subreddit feed)

```
POST https://gql-fed.reddit.com/
x-apollo-operation-id: 5f8ce513df609c3b3da05d797dbff3fa042f7761380747ee486e20e6f2aafccb
x-apollo-operation-name: SubredditFeedElements
accept: multipart/mixed; deferSpec=20220824, application/json
authorization: Bearer <access_token>
client-vendor-id: <random UUID, one per process>
x-reddit-device-id: <same UUID>
user-agent: Reddit/Version 2024.24.0/Build 1675730/Android 13
content-type: application/json; charset=utf-8
accept-encoding: gzip
```

Headers are sent lowercase, in this order — the app's captured order. `x-apollo-operation-id`
is the persisted-query hash (same value as `sha256Hash` in the body), which is how the app
fills it.

The app sends more `x-reddit-*` headers than this (`x-reddit-loid`, `x-reddit-session`,
`x-reddit-dpr`, `x-reddit-width`, `x-dev-ad-id`, `device-name`, `x-reddit-qos`, …). The
collector sends the subset above; it was sufficient for a `200` with a full feed in testing.
If the edge later tightens, the full captured header set is in `request.json` / the capture.

**`Accept` header:** unlike the previous spec, the collector now **sends** the app's
`accept: multipart/mixed; deferSpec=20220824, application/json`. The response is still a single
plain JSON document (no multipart part to parse); the header is included only to match the
app's request exactly. Parsing is unchanged.

Body (a persisted GraphQL query, sent as a hash, not the query text):

```json
{
  "operationName": "SubredditFeedElements",
  "variables": { "subredditName": "python", "sort": "NEW", "optedIn": true,
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
| `adContext`, `forceAds` | Ad targeting; ads come back as non-`SubredditPost` nodes we skip |
| the `include*` flags | Which optional fields the response embeds |

Pagination: the response's `pageInfo.endCursor` feeds an `after` variable for the next page
(not used; we fetch one page up to `MAX_POSTS`).

## Response map

Path to the post list: `data.postFeed.elements.edges[].node`. Subreddit name is
`data.postFeed.prefixedName` (`"r/Python"`).

| Post field | JSON path | Notes |
|---|---|---|
| `id` | `node.id` | e.g. `t3_1xxo1vw` |
| `title` | `node.title` | |
| `author` | `node.authorInfo.name` | `DeletedRedditor`/`[deleted]` → null |
| `commentCount` | `node.commentCount` | |
| `score` | `node.score` | |
| `createdAt` | `node.createdAt` | ISO like `2026-11-16T12:24:36.313000+0000` → ISO UTC |
| `permalink` | `node.permalink` | relative `/r/...` → absolute `https://www.reddit.com/...` |
| `previewText` | `node.content.markdown` | null for link posts; truncated to 300 chars |
| `flair` | `node.flair.text` | null when absent |
| `subreddit` | `data.postFeed.prefixedName` | without `r/` |

Node types kept: `SubredditPost` (real posts). Other node types (ads, carousels) are
**skipped** by `__typename`. `isStickied` marks pinned posts; they are kept. Parsing is
implemented and tested in `app/collector/reddit/parse_listing.py` against a scrubbed real
response (`backend/tests/fixtures/listing-new-ok.json`).

## Errors and limits

| Signal | Meaning |
|---|---|
| HTTP 401, or 403 with a JSON body | Token rejected → one token refresh, then `UPSTREAM_AUTH` |
| HTTP 403 with an HTML page | Blocked by the edge before the token is read → `UPSTREAM_BLOCKED`, no refresh or retry |
| `x-ratelimit-remaining`, `x-ratelimit-reset` (seconds) | Rate-limit budget; `reset` feeds our `Retry-After` |
| Observed limits | `x-ratelimit-used: 5`, `remaining: 295`, `reset: 211` (2026-11-16). The budget appears keyed to IP/device, not the token: a fresh token did not reset `used`. Window ≈ 10 min; the exact ceiling varies by endpoint, so pace off the live headers, not a fixed number. |
| Subreddit does not exist | HTTP **200** with `{"data":{"postFeed":null}}` (re-verified live 2026-11-17) → `NOT_FOUND_SUBREDDIT` |
| Banned or private subreddit | HTTP **200** with `postFeed.__typename == "UnavailableSubreddit"` and no other fields → `NOT_FOUND_SUBREDDIT` |
| Quarantined subreddit | A normal feed with `isQuarantined: true` and zero edges → shown as an empty feed |

## Transport fingerprint

### What the edge actually checks

The collector's requests pass through Reddit's **edge** (CDN / Fastly-Varnish) before reaching
the GraphQL backend. The edge can reject a request on its own, returning an HTML block page
with HTTP 403 *before* the token is ever read.

Testing on 2026-11-16 refined the earlier understanding of what triggers that block:

- A request with the app's **exact headers, in the app's order and casing**, succeeds (`200`)
  **even over Python's default TLS** (`http.client`, no fingerprint library). So the TLS
  fingerprint was **not**, on its own, what the edge rejected.
- The reproducible `403 Blocked` came from a client that **reordered and Title-Cased the
  headers** and added `Connection: close` (Python's `urllib.request`). The edge rejects on
  **request shape** — header order, casing, and which headers are present — more than on TLS.

This is from one IP at one time; it is what the edge did that day, not a guarantee. The edge
can tighten (including to TLS-fingerprint checks) at any time.

### What the transport sends

Given the above, the transport matches the app at **every layer** — headers *and* fingerprint
— so it stays indistinguishable from the real app even if the edge starts checking TLS:

- **Headers:** lowercase, in the app's captured order, with `default_headers=False` so
  `curl_cffi` adds none of its own. This is the part that mattered in testing.
- **TLS/HTTP-2 fingerprint:** the real app's, captured with `akamai_fp.py` — not a generic
  browser profile. (The previous transport used `curl_cffi`'s `chrome_android` profile, which
  presents **Chrome's** TLS handshake and injects Chrome client-hint headers next to a Reddit
  app `User-Agent` — an internally inconsistent request. Replaced.)

Captured fingerprint of the Reddit Android app (OkHttp 5 on Conscrypt/BoringSSL), hardcoded in
`mobile_api.py`:

| Field | Value |
|---|---|
| JA3 | `771,4865-4866-4867-49195-49199-49196-49200-52393-52392-49171-49172-156-157-47-53,0-23-65281-10-11-35-16-5-13-51-45-43-21,29-23-24,0` |
| JA3 MD5 | `1d714db2228763eab228fc28ce7f8e4f` |
| Akamai (HTTP/2) | `4:16777216\|16711681\|0\|m,p,a,s` |
| `extra_fp` | sig-algs (9, app order), `tls_min_version=4` (TLS 1.0), no GREASE, no extension permutation, `http2_no_priority` |

`curl_cffi` only enables the `status_request` TLS extension (ext 5) for its built-in browser
profiles. With a raw `ja3=` string it must be switched on explicitly
(`curl_options={CurlOpt.TLS_STATUS_REQUEST: 1}`), or the extension is dropped and the JA3 will
not match. The transport sets this.

Verified against `tls.peet.ws` (placeholder header values): the server sees JA3
`1d714db2…` and Akamai `4:16777216|16711681|0|m,p,a,s`, both matching the capture.

### Are the fingerprint fields constant?

Yes, with a caveat. They are **not time-based** and do not rotate; the constants in
`mobile_api.py` change only when edited. The fingerprint is produced by the device's TLS stack
(OkHttp + Android's Conscrypt/BoringSSL), so it stays fixed as long as that stack is fixed. It
drifts when **the app updates** or **the OS/Conscrypt TLS module updates** — on the order of
weeks/months, not hours. Freezing the app version alone is not sufficient; the system TLS
module can move under a frozen app. On the pinned emulator image, nothing updates and the
handshake is deterministic.

Two per-connection variants exist, driven by TLS **session state**, not time: a fresh
handshake ends in extension `21` (padding); a resumed one ends in `41` (`pre_shared_key`). We
pin the **fresh** variant (`…-43-21`), which is what a new connection sends.

"Constant fields" is not the same as "works forever": Reddit can deprecate the old app version
or retire the persisted-query hash **server-side** (returned as a 403 or GraphQL error, not a
fingerprint change). That — not drift of these fields — is the usual reason to re-capture.

### Re-capturing

Re-run the capture (see [Capture setup](#capture-setup)) with `mitmdump -s akamai_fp.py -w
capture.flows`; read the JA3 / Akamai / `extra_fp` for a `gql-fed.reddit.com` connection from
`akamai_fp.jsonl`, and update the constants in `mobile_api.py`. `test_reddit_calls.py
--check-fp` confirms the live request matches the captured values.

## Compliance note

This replays the **mobile app's own** requests: its public client id, its anonymous token
flow, and its internal GraphQL endpoint (`gql-fed.reddit.com`) with a persisted-query hash. It
is not the official developer API (no registered developer app, no `*.json` public endpoints,
no PRAW/snoowrap), and no browser or automation drives the app. `scripts/check-compliance.sh`
enforces this and allows the Reddit hosts named above with a pointer to this file.

Using the app's private endpoints and client id instead of the official API is contrary to
Reddit's API terms; this is a policy risk to the project/account independent of whether the
requests technically succeed. Reddit's rate limits (above) and any future attestation or
request-signing on these endpoints would end this access regardless of fingerprint.
