import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import type { Database } from 'better-sqlite3';
import { openDatabase } from '../../../src/db/connection.js';
import { ensureSchema } from '../../../src/db/schema.js';
import { createRepository, type CollectionRepository } from '../../../src/db/repository.js';
import { AppError } from '../../../src/errors.js';
import { FakeClock, makeLogger, makePost } from '../../helpers.js';

let db: Database;
let clock: FakeClock;
let repo: CollectionRepository;

beforeEach(() => {
  db = openDatabase(':memory:');
  ensureSchema(db);
  clock = new FakeClock();
  repo = createRepository(db, clock, makeLogger().logger);
});
afterEach(() => {
  if (db.open) db.close();
});

const count = (table: string) =>
  (db.prepare(`SELECT COUNT(*) AS n FROM ${table}`).get() as { n: number }).n;

describe('recordSuccess', () => {
  it('stores the posts and returns a summary stamped with the finish time', () => {
    const startedAt = clock.now();
    clock.advanceSeconds(2);

    const summary = repo.recordSuccess('ubisoft', [makePost('t3_a'), makePost('t3_b')], startedAt);

    expect(summary).toEqual({
      id: expect.any(Number),
      term: 'ubisoft',
      postCount: 2,
      collectedAt: '2026-10-29T12:00:02.000Z',
    });
    expect(
      repo
        .getFeed(summary.id)
        .map((p) => p.id)
        .sort(),
    ).toEqual(['t3_a', 't3_b']);
  });

  it('does not duplicate posts across runs and refreshes their counts', () => {
    repo.recordSuccess('ubisoft', [makePost('t3_a', { commentCount: 1 })], clock.now());
    clock.advanceSeconds(60);
    const second = repo.recordSuccess(
      'ubisoft',
      [makePost('t3_a', { commentCount: 9, title: 'Edited' })],
      clock.now(),
    );

    expect(count('posts')).toBe(1);
    expect(count('collections')).toBe(2);
    expect(repo.getFeed(second.id)[0]).toMatchObject({ commentCount: 9, title: 'Edited' });
  });

  it('keeps first_seen_at and moves last_seen_at on re-collection', () => {
    repo.recordSuccess('ubisoft', [makePost('t3_a')], clock.now());
    clock.advanceSeconds(60);
    repo.recordSuccess('ubisoft', [makePost('t3_a')], clock.now());

    expect(db.prepare('SELECT first_seen_at, last_seen_at FROM posts').get()).toEqual({
      first_seen_at: '2026-10-29T12:00:00.000Z',
      last_seen_at: '2026-10-29T12:01:00.000Z',
    });
  });

  it('stores one row for a post returned under two terms, linked from both runs', () => {
    const a = repo.recordSuccess('ubisoft', [makePost('t3_shared')], clock.now());
    const b = repo.recordSuccess('gaming', [makePost('t3_shared')], clock.now());

    expect(count('posts')).toBe(1);
    expect(repo.getFeed(a.id)).toHaveLength(1);
    expect(repo.getFeed(b.id)).toHaveLength(1);
  });

  it('records an empty run as a success with zero posts', () => {
    const summary = repo.recordSuccess('quiet', [], clock.now());

    expect(summary.postCount).toBe(0);
    expect(repo.getFeed(summary.id)).toEqual([]);
  });

  it('writes nothing when any post in the run fails to insert', () => {
    const bad = makePost('t3_bad', { commentCount: -1 });

    expect(() => repo.recordSuccess('ubisoft', [makePost('t3_ok'), bad], clock.now())).toThrow();
    expect(count('posts')).toBe(0);
    expect(count('collections')).toBe(0);
    expect(count('collection_posts')).toBe(0);
  });

  it('ignores a repeated post id within one run', () => {
    const summary = repo.recordSuccess(
      'ubisoft',
      [makePost('t3_a'), makePost('t3_a')],
      clock.now(),
    );
    expect(repo.getFeed(summary.id)).toHaveLength(1);
  });
});

describe('getFeed', () => {
  it('orders newest first with reddit_id as a deterministic tie-breaker', () => {
    const summary = repo.recordSuccess(
      'ubisoft',
      [
        makePost('t3_b', { createdAt: '2026-10-29T09:00:00.000Z' }),
        makePost('t3_c', { createdAt: '2026-10-29T11:00:00.000Z' }),
        makePost('t3_a', { createdAt: '2026-10-29T09:00:00.000Z' }),
      ],
      clock.now(),
    );

    expect(repo.getFeed(summary.id).map((p) => p.id)).toEqual(['t3_c', 't3_a', 't3_b']);
  });
});

describe('recordFailure', () => {
  it('stores a failed run without changing the latest successful feed', () => {
    const good = repo.recordSuccess('ubisoft', [makePost('t3_a')], clock.now());
    clock.advanceSeconds(30);

    repo.recordFailure('ubisoft', 'UPSTREAM_TIMEOUT', clock.now());

    expect(
      db
        .prepare("SELECT status, error_code, post_count FROM collections WHERE status = 'failed'")
        .get(),
    ).toEqual({ status: 'failed', error_code: 'UPSTREAM_TIMEOUT', post_count: 0 });
    expect(repo.getLatestSuccess('ubisoft')?.id).toBe(good.id);
  });

  it('never throws, and logs instead, when the write itself fails', () => {
    const { entries, logger } = makeLogger();
    const failing = createRepository(db, clock, logger);
    db.close();

    expect(() => failing.recordFailure('ubisoft', 'UPSTREAM_ERROR', clock.now())).not.toThrow();
    expect(entries.map((e) => e.level)).toContain('error');
  });
});

describe('getLatestSuccess', () => {
  it('returns null for a term that was never collected', () => {
    expect(repo.getLatestSuccess('never')).toBeNull();
  });

  it('returns the newest successful run of that term only', () => {
    repo.recordSuccess('ubisoft', [makePost('t3_a')], clock.now());
    clock.advanceSeconds(10);
    const newer = repo.recordSuccess('ubisoft', [makePost('t3_b')], clock.now());
    repo.recordSuccess('gaming', [makePost('t3_c')], clock.now());

    expect(repo.getLatestSuccess('ubisoft')).toMatchObject({ id: newer.id, term: 'ubisoft' });
    expect(repo.getFeed(newer.id).map((p) => p.id)).toEqual(['t3_b']);
  });
});

describe('getFreshSuccess', () => {
  it('returns the latest success while it is younger than the TTL', () => {
    const run = repo.recordSuccess('ubisoft', [makePost('t3_a')], clock.now());
    clock.advanceSeconds(59);

    expect(repo.getFreshSuccess('ubisoft', 60)?.id).toBe(run.id);
  });

  it('returns null once the TTL has passed', () => {
    repo.recordSuccess('ubisoft', [makePost('t3_a')], clock.now());
    clock.advanceSeconds(61);

    expect(repo.getFreshSuccess('ubisoft', 60)).toBeNull();
  });

  it('always returns null when the TTL is zero', () => {
    repo.recordSuccess('ubisoft', [makePost('t3_a')], clock.now());
    expect(repo.getFreshSuccess('ubisoft', 0)).toBeNull();
  });
});

describe('ping', () => {
  it('succeeds on an open database', () => {
    expect(() => repo.ping()).not.toThrow();
  });
});

describe('database failures', () => {
  it.each([
    ['getFeed', (r: CollectionRepository) => r.getFeed(1)],
    ['getLatestSuccess', (r: CollectionRepository) => r.getLatestSuccess('x')],
    ['getFreshSuccess', (r: CollectionRepository) => r.getFreshSuccess('x', 60)],
    ['recordSuccess', (r: CollectionRepository) => r.recordSuccess('x', [], new Date())],
    ['ping', (r: CollectionRepository) => r.ping()],
  ])('%s raises DB_ERROR with the SQLite error kept only as the cause', (_name, call) => {
    db.close();

    let thrown: unknown;
    try {
      call(repo);
    } catch (error) {
      thrown = error;
    }

    expect(thrown).toBeInstanceOf(AppError);
    expect(thrown).toMatchObject({ code: 'DB_ERROR', message: 'Could not save results locally.' });
    expect((thrown as AppError).cause).toBeInstanceOf(Error);
  });
});
