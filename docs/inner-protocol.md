# Collector protocol (web service ↔ inner server)

The Python collector (`backend/app/inner/`) listens on `INNER_HOST:INNER_PORT`
(default `127.0.0.1:3002`) and speaks one-line JSON over TCP. The Express web service
(`server/src/innerClient.js`) is its only intended client. Both bind to localhost.

## Framing

- One request per TCP connection.
- The client sends one UTF-8 JSON object followed by `\n`; the server answers with one JSON
  object followed by `\n`, then closes the connection.
- The request line may be at most **4096 bytes** (newline excluded). A longer line gets an
  `INVALID_REQUEST` reply.
- The whole request line must arrive within **5 seconds**, otherwise the server closes the
  connection without a reply. A client that closes before sending `\n` gets no reply.
- When every worker thread is busy and 64 more connections are already waiting, a new
  connection gets a `BUSY` reply at once instead of waiting.

## Request

```json
{"v": 1, "command": "GET", "resource": "posts", "args": {"term": "r/ubisoft", "freshness": "auto"}}
{"v": 1, "command": "GET", "resource": "health"}
```

| Field | Meaning |
|---|---|
| `v` | Protocol version; must be the number `1` |
| `command` | A CRUD verb; only `GET` is supported (case-insensitive) |
| `resource` | `posts` or `health` |
| `args` | Optional object. For `posts`: `term` (required string, at most 200 characters before normalizing) and `freshness` (`auto` default, `live`, or `stored`) |

`freshness`: `auto` returns a stored collection younger than `COLLECTION_TTL_SECONDS`,
otherwise collects live first; `live` always collects; `stored` never calls Reddit.

## Reply

Success:

```json
{"ok": true, "result": {"collection": {"id": 3, "term": "ubisoft", "source": "live", "collectedAt": "2026-10-31T14:55:24.992Z", "postCount": 25}, "posts": [ ... ]}}
{"ok": true, "result": {"status": "ok", "db": "ok", "collectorMode": "live", "staleAfterSeconds": 600}}
```

For `posts` with `freshness=stored` and a term never collected, `result` is
`{"collection": null, "posts": []}`.

Failure:

```json
{"ok": false, "error": {"code": "RATE_LIMITED", "message": "Reddit is limiting requests. Try again in 30 seconds.", "retryable": true, "retryAfterSeconds": 30}, "lastGood": {"collection": {...}, "posts": [...]}}
```

`lastGood` is present only when a collection failed and an earlier successful feed for the
same term exists. `retryAfterSeconds` is present only for rate limits.

| Code | Meaning | `retryable` |
|---|---|---|
| `INVALID_REQUEST` | Not valid JSON, wrong `v`, unknown command or resource, bad arguments, line too long | no |
| `INVALID_TERM` | The term is not a valid subreddit name | no |
| `NOT_FOUND_SUBREDDIT` | The subreddit does not exist, or is banned or private | no |
| `RATE_LIMITED` | Reddit returned 429 | yes |
| `UPSTREAM_AUTH` | Reddit rejected the anonymous token | yes |
| `UPSTREAM_ERROR` | Reddit failed or could not be reached | yes |
| `UPSTREAM_TIMEOUT` | Reddit (or the collection) took too long | yes |
| `CONTRACT_ERROR` | Reddit's response had an unexpected shape | yes |
| `DB_ERROR` | The local database failed | yes |
| `INTERNAL` | An unexpected error (details are only logged) | yes |
| `BUSY` | Too many connections are already waiting; nothing was done | yes |

HTTP status codes are not part of this protocol; the web service maps codes to statuses
(`server/src/errors.js`).

## Trying it by hand

The interactive client (`npm run client`, code in `backend/app/client/`) sends these messages
and prints the replies as text or JSON; see the README, "Talking to the collector directly".
With `nc`:

```bash
printf '{"v":1,"command":"GET","resource":"posts","args":{"term":"r/ubisoft"}}\n' | nc 127.0.0.1 3002
printf '{"v":1,"command":"GET","resource":"health"}\n' | nc 127.0.0.1 3002
```
