import { mkdirSync } from 'node:fs';
import { dirname } from 'node:path';
import BetterSqlite3, { type Database } from 'better-sqlite3';

export const IN_MEMORY = ':memory:';

export function openDatabase(path: string): Database {
  if (path !== IN_MEMORY) {
    mkdirSync(dirname(path), { recursive: true });
  }
  const db = new BetterSqlite3(path);
  db.pragma('journal_mode = WAL');
  db.pragma('foreign_keys = ON');
  db.pragma('busy_timeout = 5000');
  db.pragma('synchronous = NORMAL');
  return db;
}
