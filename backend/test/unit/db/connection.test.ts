import { existsSync, mkdtempSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { afterEach, describe, expect, it } from 'vitest';
import type { Database } from 'better-sqlite3';
import { openDatabase } from '../../../src/db/connection.js';

let db: Database | undefined;
afterEach(() => db?.close());

describe('openDatabase', () => {
  it('creates missing parent directories and the file', () => {
    const path = join(mkdtempSync(join(tmpdir(), 'db-')), 'nested', 'dir', 'test.db');

    db = openDatabase(path);

    expect(existsSync(path)).toBe(true);
  });

  it('enables WAL, foreign keys and a busy timeout on a file database', () => {
    db = openDatabase(join(mkdtempSync(join(tmpdir(), 'db-')), 'test.db'));

    expect(db.pragma('journal_mode', { simple: true })).toBe('wal');
    expect(db.pragma('foreign_keys', { simple: true })).toBe(1);
    expect(db.pragma('busy_timeout', { simple: true })).toBe(5000);
    expect(db.pragma('synchronous', { simple: true })).toBe(1);
  });

  it('opens an in-memory database without touching the filesystem', () => {
    db = openDatabase(':memory:');
    expect(db.pragma('foreign_keys', { simple: true })).toBe(1);
  });
});
