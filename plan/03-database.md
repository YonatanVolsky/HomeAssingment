# 03 Database

## Goal and dependencies

A local SQLite database that stores posts, collection runs, and which posts each
run returned, with a small repository API that the service layer uses. Depends
on `00` (config, errors, contracts). Independent of the scraper, so it can be
built while capture is in progress.

## Design summary

- One file (`DB_PATH`), created on first start, no external service.
- Three tables: `posts`, `collections`, `collection_posts`.
- Posts are upserted by `reddit_id`; each run records which posts it returned.
- The feed for a term is the post set of that term's latest **successful** run.
- Failed runs are recorded and never replace the last good feed.
- One `schema.sql` file applied at startup when `PRAGMA user_version` is 0,
  then `user_version` is set to 1. No migration framework (cut for time).
- No retention prune (cut for time). Growth is one row per live collection plus
  its links, and posts are de-duplicated, so a local demo stays small. Listed
  as a limitation in 07.

## Step-by-step plan

1. Work on `feat/app`.
2. **Connection factory** `openDatabase(path)`: create parent dir, open, set PRAGMAs.
3. **`ensureSchema(db)`** and `schema.sql`. Test on an empty file and on a file
   that already has the schema (idempotent).
4. **Row mappers** between DB rows (snake_case) and contract types (camelCase).
5. **`upsertPosts`** inside a transaction helper. Tests: insert, update counts,
   `first_seen_at` preserved.
6. **`recordSuccess`**: one transaction that upserts posts, inserts the
   collection row, inserts links with `position`. Test atomicity with an
   injected failure.
7. **`recordFailure`**: inserts a failed collection row.
8. **Queries**: `getLatestSuccess(term)`, `getFeed(collectionId)`,
   `getFreshSuccess(term, ttlSeconds)` (current time from the injected clock).
9. **DB error wrapper**: map `SqliteError` to `AppError(DB_ERROR)`, keeping the
    cause for logs only.
10. **Inspection script** `scripts/db-inspect.sh` (prints counts and the latest
    runs via the `sqlite3` CLI, which ships with macOS), used in the demo to
    prove persistence.

## Entities

### Connection and PRAGMAs (`db/connection.ts`)

| Setting | Value | Why |
|---|---|---|
| `journal_mode` | `WAL` | Readers do not block the writer |
| `foreign_keys` | `ON` | Cascades and integrity are enforced (off by default in SQLite) |
| `busy_timeout` | `5000` | Avoid immediate "database is locked" |
| `synchronous` | `NORMAL` | Safe with WAL, faster |

All queries use prepared statements with bound parameters. No string
concatenation of user input anywhere.

### Schema (`db/schema.sql`)

```sql
CREATE TABLE posts (
  id             INTEGER PRIMARY KEY,
  reddit_id      TEXT    NOT NULL UNIQUE,
  title          TEXT    NOT NULL,
  author         TEXT,
  comment_count  INTEGER NOT NULL DEFAULT 0 CHECK (comment_count >= 0),
  score          INTEGER NOT NULL DEFAULT 0,
  created_at     TEXT    NOT NULL,
  permalink      TEXT    NOT NULL,
  subreddit      TEXT,
  preview_text   TEXT,
  flair          TEXT,
  first_seen_at  TEXT    NOT NULL,
  last_seen_at   TEXT    NOT NULL
);
CREATE INDEX idx_posts_created_at ON posts (created_at DESC);

CREATE TABLE collections (
  id           INTEGER PRIMARY KEY,
  term         TEXT    NOT NULL,
  status       TEXT    NOT NULL CHECK (status IN ('success', 'failed')),
  post_count   INTEGER NOT NULL DEFAULT 0 CHECK (post_count >= 0),
  error_code   TEXT,
  started_at   TEXT    NOT NULL,
  finished_at  TEXT    NOT NULL
);
CREATE INDEX idx_collections_term_status_finished
  ON collections (term, status, finished_at DESC);

CREATE TABLE collection_posts (
  collection_id INTEGER NOT NULL REFERENCES collections (id) ON DELETE CASCADE,
  post_id       INTEGER NOT NULL REFERENCES posts (id)       ON DELETE CASCADE,
  position      INTEGER NOT NULL,
  PRIMARY KEY (collection_id, post_id)
);
CREATE INDEX idx_collection_posts_post ON collection_posts (post_id);
```

Notes on choices:

- Timestamps are ISO UTC text, which sorts correctly as text and is
  human-readable in the DB inspector.
- `reddit_id` is the natural key; the integer `id` is the internal key used by
  the join table.
- `error_code` is stored for failed runs so history is explainable; messages
  are not stored.
- No `raw_json` column: fixtures cover debugging and it avoids storing large
  payloads.
- `PRAGMA user_version` is set to 1 after the schema is applied. A future
  change would add a `user_version = 2` step to `ensureSchema`.

### Tables in detail

| Table | Row means | Written when | Mutability |
|---|---|---|---|
| `posts` | One Reddit post, ever seen | Every successful run (upsert) | Counts, title, score, preview, flair, `last_seen_at` refresh; `reddit_id`, `created_at`, `first_seen_at` never change |
| `collections` | One attempt for a term | Every run that reached the collector (success or failure). Cache hits do **not** create rows | Immutable after insert |
| `collection_posts` | "run X returned post Y at position P" | With the successful run | Immutable |

Validation failures (`INVALID_TERM`) are rejected before any run and are not
recorded.

### Repository API (`db/repository.ts`)

All functions take the `Database` handle at construction (`createRepository(db, clock)`),
and accept a `clock` so tests control time.

| Function | Behavior |
|---|---|
| `recordSuccess(term, posts, startedAt): CollectionSummary` | One transaction: upsert each post (`INSERT ... ON CONFLICT(reddit_id) DO UPDATE SET title, author, comment_count, score, permalink, subreddit, preview_text, flair, last_seen_at`; `first_seen_at` untouched), insert the collection row (`status='success'`, `post_count`), insert links with `position` 0..n-1. Rolls back entirely on any error. Returns the summary |
| `recordFailure(term, errorCode, startedAt): void` | Inserts a `failed` row with `post_count = 0`. Never throws to the caller if it fails itself (logs instead), so a failed insert cannot hide the original error |
| `getLatestSuccess(term): CollectionSummary or null` | `ORDER BY finished_at DESC, id DESC LIMIT 1` over successful rows |
| `getFreshSuccess(term, ttlSeconds): CollectionSummary or null` | Latest success whose `finished_at >= clock.now() - ttl`; `ttl = 0` always returns `null` |
| `getFeed(collectionId): Post[]` | Join `collection_posts` to `posts`; `ORDER BY posts.created_at DESC, posts.reddit_id ASC` |
| `ping(): void` | `SELECT 1`, used by `/api/health` |

Summaries returned by the repository do not carry `source`; the service sets
`source` (`live` or `cache`) depending on how the result was produced.

Feed ordering: newest first by creation time, `reddit_id` as a deterministic
tie-breaker. `position` is kept for auditing what Reddit returned and is not
used for display.

### Behavior matrix

| Scenario | Result |
|---|---|
| Same term collected twice | 2 collection rows, posts upserted (no duplicates), feed = second run |
| Post appears under two terms | One `posts` row, linked from both runs |
| Second run fails | Failed row added, feed for the term still the first run |
| Process dies mid-write | Transaction rolled back, no partial run visible |
| Subreddit returns zero posts | Success row with `post_count = 0`, empty feed (not an error) |

## Version control plan

- Branch: `feat/app`.
- Commits, in order:
  1. `feat(db): add connection factory with pragmas`
  2. `feat(db): add schema and ensureSchema`
  3. `feat(db): add row mappers`
  4. `feat(db): add transactional recordSuccess with post upsert`
  5. `feat(db): add recordFailure and feed queries`
  6. `feat(db): wrap sqlite errors as DB_ERROR`
  7. `chore(scripts): add db-inspect helper`
- Before submission, `schema.sql` may be edited freely (delete `data/` locally
  after a change). There is no deployed data to migrate.
- Done when: repository tests pass on a temp-file DB and on `:memory:`.

## Definition of done

- [ ] Fresh machine: starting the app creates `data/collector.db` with the schema.
- [ ] Re-running a collection never duplicates posts (`reddit_id` unique).
- [ ] Atomicity test passes (injected failure leaves no partial run).
- [ ] Failed run does not change the feed.
- [ ] No query built by string concatenation (checked in review).
