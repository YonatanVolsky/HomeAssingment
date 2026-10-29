import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import type { Database } from 'better-sqlite3';
import { CollectionService } from '../../../src/services/collectionService.js';
import { AppError } from '../../../src/errors.js';
import { FakeClock, makeLogger, makePost } from '../../helpers.js';
import { FakeCollector, memoryRepository } from '../../fakes.js';

let clock: FakeClock;
let collector: FakeCollector;
let db: Database;
let service: CollectionService;

beforeEach(() => {
  clock = new FakeClock();
  collector = new FakeCollector();
  collector.next = async () => [makePost('t3_a'), makePost('t3_b')];
  const memory = memoryRepository(clock);
  db = memory.db;
  service = new CollectionService({
    repository: memory.repository,
    collector,
    clock,
    config: { maxPosts: 25, collectionTtlSeconds: 60 },
    logger: makeLogger().logger,
  });
});
afterEach(() => {
  if (db.open) db.close();
});

const runs = (status: string) =>
  (
    db.prepare('SELECT COUNT(*) AS n FROM collections WHERE status = ?').get(status) as {
      n: number;
    }
  ).n;

describe('CollectionService.collect', () => {
  it('collects live, stores the run and returns what was stored', async () => {
    const response = await service.collect('r/Ubisoft', false);

    expect(collector.calls).toEqual([{ subreddit: 'ubisoft', limit: 25 }]);
    expect(response.collection).toMatchObject({ term: 'ubisoft', source: 'live', postCount: 2 });
    expect(response.posts.map((p) => p.id).sort()).toEqual(['t3_a', 't3_b']);
    expect(runs('success')).toBe(1);
  });

  it('rejects an invalid term before calling Reddit or writing anything', async () => {
    await expect(service.collect('bad name!', false)).rejects.toMatchObject({
      code: 'INVALID_TERM',
    });
    expect(collector.calls).toHaveLength(0);
    expect(runs('failed')).toBe(0);
  });

  it('serves a fresh collection from the cache without calling Reddit', async () => {
    await service.collect('ubisoft', false);
    clock.advanceSeconds(30);

    const response = await service.collect('ubisoft', false);

    expect(collector.calls).toHaveLength(1);
    expect(response.collection?.source).toBe('cache');
    expect(response.posts).toHaveLength(2);
    expect(runs('success')).toBe(1);
  });

  it('collects live again once the cache is older than the TTL', async () => {
    await service.collect('ubisoft', false);
    clock.advanceSeconds(61);

    expect((await service.collect('ubisoft', false)).collection?.source).toBe('live');
    expect(collector.calls).toHaveLength(2);
  });

  it('bypasses the cache when forced', async () => {
    await service.collect('ubisoft', false);

    expect((await service.collect('ubisoft', true)).collection?.source).toBe('live');
    expect(collector.calls).toHaveLength(2);
  });

  it('shares one collection between concurrent requests for the same term', async () => {
    collector.hold();
    const first = service.collect('ubisoft', false);
    const second = service.collect('r/ubisoft', true);
    collector.open();

    const [a, b] = await Promise.all([first, second]);

    expect(collector.calls).toHaveLength(1);
    expect(a.collection?.id).toBe(b.collection?.id);
  });

  it('runs collections for different terms independently', async () => {
    await Promise.all([service.collect('ubisoft', false), service.collect('gaming', false)]);
    expect(collector.calls.map((c) => c.subreddit).sort()).toEqual(['gaming', 'ubisoft']);
  });

  it('allows a new collection after the previous one finished', async () => {
    await service.collect('ubisoft', true);
    await service.collect('ubisoft', true);
    expect(collector.calls).toHaveLength(2);
  });

  it('records a failed run and rethrows the collector error', async () => {
    collector.next = async () => {
      throw new AppError('UPSTREAM_TIMEOUT');
    };

    await expect(service.collect('ubisoft', false)).rejects.toMatchObject({
      code: 'UPSTREAM_TIMEOUT',
    });
    expect(db.prepare("SELECT error_code FROM collections WHERE status = 'failed'").get()).toEqual({
      error_code: 'UPSTREAM_TIMEOUT',
    });
  });

  it('reports an unexpected collector exception as INTERNAL', async () => {
    collector.next = async () => {
      throw new TypeError('boom');
    };
    await expect(service.collect('ubisoft', false)).rejects.toMatchObject({ code: 'INTERNAL' });
    expect(runs('failed')).toBe(1);
  });

  it('reports a failed database write as DB_ERROR, not as a success', async () => {
    collector.next = async () => [makePost('t3_bad', { commentCount: -1 })];

    await expect(service.collect('ubisoft', false)).rejects.toMatchObject({ code: 'DB_ERROR' });
    expect(runs('success')).toBe(0);
    expect(runs('failed')).toBe(1);
  });

  it('treats zero posts as a successful, empty collection', async () => {
    collector.next = async () => [];

    const response = await service.collect('quiet', false);

    expect(response).toMatchObject({ collection: { postCount: 0, source: 'live' }, posts: [] });
  });
});

describe('CollectionService.lastGood', () => {
  it('returns the previous successful feed for the term, marked as cache', async () => {
    await service.collect('ubisoft', false);
    expect(service.lastGood('r/UBISOFT')).toMatchObject({
      collection: { source: 'cache', term: 'ubisoft' },
      posts: expect.any(Array),
    });
  });

  it('returns undefined when there is none or the term is invalid', () => {
    expect(service.lastGood('ubisoft')).toBeUndefined();
    expect(service.lastGood('bad name!')).toBeUndefined();
  });

  it('returns undefined instead of throwing when the database fails', async () => {
    await service.collect('ubisoft', false);
    db.close();
    expect(service.lastGood('ubisoft')).toBeUndefined();
  });
});

describe('CollectionService.getPosts', () => {
  it('returns an empty response for a term never collected', () => {
    expect(service.getPosts('ubisoft')).toEqual({ collection: null, posts: [] });
  });

  it('returns the latest stored feed without calling Reddit', async () => {
    await service.collect('ubisoft', false);
    clock.advanceSeconds(3600);

    const response = service.getPosts('ubisoft');

    expect(response.collection?.source).toBe('cache');
    expect(response.posts).toHaveLength(2);
    expect(collector.calls).toHaveLength(1);
  });

  it('rejects an invalid term', () => {
    expect(() => service.getPosts('r/')).toThrow(expect.objectContaining({ code: 'INVALID_TERM' }));
  });
});
