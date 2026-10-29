import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import type { Database } from 'better-sqlite3';
import { openDatabase } from '../../../src/db/connection.js';
import { ensureSchema, SCHEMA_VERSION } from '../../../src/db/schema.js';

let db: Database;
beforeEach(() => {
  db = openDatabase(':memory:');
});
afterEach(() => db.close());

const tableNames = () =>
  (db.prepare("SELECT name FROM sqlite_master WHERE type = 'table' ORDER BY name").all() as {
    name: string;
  }[]).map((row) => row.name);

describe('ensureSchema', () => {
  it('creates the three tables and sets user_version', () => {
    ensureSchema(db);

    expect(tableNames()).toEqual(['collection_posts', 'collections', 'posts']);
    expect(db.pragma('user_version', { simple: true })).toBe(SCHEMA_VERSION);
  });

  it('is idempotent and keeps existing rows', () => {
    ensureSchema(db);
    db.prepare(
      `INSERT INTO collections (term, status, post_count, started_at, finished_at)
       VALUES ('ubisoft', 'success', 0, 'a', 'b')`,
    ).run();

    ensureSchema(db);

    expect(db.prepare('SELECT COUNT(*) AS n FROM collections').get()).toEqual({ n: 1 });
  });

  it('rejects a second post with the same reddit_id', () => {
    ensureSchema(db);
    const insert = db.prepare(
      `INSERT INTO posts (reddit_id, title, created_at, permalink, first_seen_at, last_seen_at)
       VALUES ('t3_a', 'x', 'c', 'p', 'f', 'l')`,
    );
    insert.run();

    expect(() => insert.run()).toThrow(/UNIQUE/);
  });

  it('rejects an unknown collection status', () => {
    ensureSchema(db);
    expect(() =>
      db
        .prepare(
          `INSERT INTO collections (term, status, started_at, finished_at)
           VALUES ('x', 'pending', 'a', 'b')`,
        )
        .run(),
    ).toThrow(/CHECK/);
  });
});
