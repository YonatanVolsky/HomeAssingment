import sqlite3

SCHEMA_VERSION = 1

_SCHEMA_V1 = """
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
"""


def ensure_schema(db: sqlite3.Connection) -> None:
    """Applies the schema to a new database. A later change adds a `version < 2` step."""
    version = db.execute('PRAGMA user_version').fetchone()[0]
    if version >= SCHEMA_VERSION:
        return
    db.executescript(f'BEGIN; {_SCHEMA_V1} PRAGMA user_version = {SCHEMA_VERSION}; COMMIT;')
