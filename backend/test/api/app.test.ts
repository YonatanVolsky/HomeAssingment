import { Writable } from 'node:stream';
import type { FastifyInstance } from 'fastify';
import type { Database } from 'better-sqlite3';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { buildApp } from '../../src/app.js';
import { loadConfig } from '../../src/config.js';
import { AppError } from '../../src/errors.js';
import { FakeClock, makePost } from '../helpers.js';
import { FakeCollector, memoryRepository } from '../fakes.js';

let app: FastifyInstance;
let db: Database;
let clock: FakeClock;
let collector: FakeCollector;
let logLines: string[];

beforeEach(async () => {
  clock = new FakeClock();
  collector = new FakeCollector();
  collector.next = async () => [makePost('t3_a'), makePost('t3_b')];
  const memory = memoryRepository(clock);
  db = memory.db;
  logLines = [];
  const stream = new Writable({
    write(chunk, _encoding, done) {
      logLines.push(String(chunk));
      done();
    },
  });
  app = await buildApp({
    repository: memory.repository,
    collector,
    clock,
    config: loadConfig({ STALE_AFTER_SECONDS: '600' }),
    logger: { level: 'info', stream },
  });
});
afterEach(async () => {
  await app.close();
  if (db.open) db.close();
});

const post = (body: unknown) =>
  app.inject({ method: 'POST', url: '/api/collections', payload: body as object });

const failWith = (error: Error) => {
  collector.next = async () => {
    throw error;
  };
};

describe('GET /api/health', () => {
  it('reports ok with the collector mode and stale threshold', async () => {
    const response = await app.inject({ method: 'GET', url: '/api/health' });

    expect(response.statusCode).toBe(200);
    expect(response.json()).toEqual({
      status: 'ok',
      db: 'ok',
      collectorMode: 'live',
      staleAfterSeconds: 600,
    });
  });

  it('returns 503 when the database is unavailable', async () => {
    db.close();
    const response = await app.inject({ method: 'GET', url: '/api/health' });

    expect(response.statusCode).toBe(503);
    expect(response.json()).toMatchObject({ status: 'error', db: 'error' });
  });
});

describe('POST /api/collections', () => {
  it('collects live and returns the stored posts', async () => {
    const response = await post({ term: 'r/ubisoft' });

    expect(response.statusCode).toBe(200);
    expect(response.json()).toMatchObject({
      collection: { term: 'ubisoft', source: 'live', postCount: 2 },
      posts: [expect.objectContaining({ id: expect.any(String) }), expect.anything()],
    });
  });

  it('serves a repeat request from the cache and a forced one live', async () => {
    await post({ term: 'ubisoft' });

    expect((await post({ term: 'ubisoft' })).json().collection.source).toBe('cache');
    expect((await post({ term: 'ubisoft', force: true })).json().collection.source).toBe('live');
    expect(collector.calls).toHaveLength(2);
  });

  it('returns 200 with an empty list when the subreddit has no posts', async () => {
    collector.next = async () => [];
    const response = await post({ term: 'quiet' });

    expect(response.statusCode).toBe(200);
    expect(response.json()).toMatchObject({ collection: { postCount: 0 }, posts: [] });
  });

  it('makes one collector call for two simultaneous requests', async () => {
    collector.hold();
    const both = Promise.all([post({ term: 'ubisoft' }), post({ term: 'ubisoft' })]);
    await new Promise((resolve) => setTimeout(resolve, 20));
    collector.open();

    const [a, b] = await both;
    expect(collector.calls).toHaveLength(1);
    expect(a.json().collection.id).toBe(b.json().collection.id);
  });

  it.each([
    ['a missing term', {}],
    ['a non-string term', { term: 42 }],
    ['an empty term', { term: '' }],
    ['an over-long term', { term: 'x'.repeat(201) }],
    ['an invalid subreddit name', { term: 'r/' }],
    ['a non-boolean force', { term: 'ubisoft', force: 'yes' }],
  ])('rejects %s with 400 INVALID_TERM', async (_label, body) => {
    const response = await post(body);

    expect(response.statusCode).toBe(400);
    expect(response.json()).toEqual({
      error: { code: 'INVALID_TERM', message: expect.any(String), retryable: false },
    });
    expect(collector.calls).toHaveLength(0);
  });

  it('rejects malformed JSON with 400 INVALID_TERM', async () => {
    const response = await app.inject({
      method: 'POST',
      url: '/api/collections',
      headers: { 'content-type': 'application/json' },
      payload: '{"term":',
    });
    expect(response.statusCode).toBe(400);
    expect(response.json().error.code).toBe('INVALID_TERM');
  });

  it('rejects a body over 1 KB', async () => {
    const response = await post({ term: 'ubisoft', padding: 'x'.repeat(2000) });
    expect(response.statusCode).toBe(400);
    expect(response.json().error.code).toBe('INVALID_TERM');
  });

  it.each([
    ['NOT_FOUND_SUBREDDIT', 404, false],
    ['UPSTREAM_AUTH', 502, true],
    ['UPSTREAM_ERROR', 502, true],
    ['UPSTREAM_TIMEOUT', 504, true],
    ['CONTRACT_ERROR', 502, true],
  ] as const)('maps %s to HTTP %i (retryable %s)', async (code, status, retryable) => {
    failWith(new AppError(code));
    const response = await post({ term: 'ubisoft' });

    expect(response.statusCode).toBe(status);
    expect(response.json().error).toMatchObject({ code, retryable });
  });

  it('returns 429 with a Retry-After header when Reddit rate-limits', async () => {
    failWith(new AppError('RATE_LIMITED', undefined, { retryAfterSeconds: 17 }));
    const response = await post({ term: 'ubisoft' });

    expect(response.statusCode).toBe(429);
    expect(response.headers['retry-after']).toBe('17');
    expect(response.json().error).toMatchObject({ code: 'RATE_LIMITED', retryAfterSeconds: 17 });
  });

  it('returns 500 DB_ERROR when the results cannot be saved', async () => {
    collector.next = async () => [makePost('t3_bad', { commentCount: -1 })];
    const response = await post({ term: 'ubisoft' });

    expect(response.statusCode).toBe(500);
    expect(response.json().error.code).toBe('DB_ERROR');
  });

  it('attaches the last good feed to an upstream error', async () => {
    await post({ term: 'ubisoft' });
    failWith(new AppError('UPSTREAM_TIMEOUT'));

    const response = await post({ term: 'ubisoft', force: true });

    expect(response.statusCode).toBe(504);
    expect(response.json().lastGood).toMatchObject({
      collection: { source: 'cache', term: 'ubisoft' },
      posts: expect.any(Array),
    });
  });

  it('does not attach lastGood when nothing was collected before', async () => {
    failWith(new AppError('UPSTREAM_TIMEOUT'));
    expect((await post({ term: 'ubisoft' })).json()).not.toHaveProperty('lastGood');
  });

  it('never leaks causes, stack traces or tokens in the response', async () => {
    failWith(
      new AppError('UPSTREAM_AUTH', undefined, { cause: new Error('Bearer secret-token-123') }),
    );
    const body = (await post({ term: 'ubisoft' })).body;

    expect(body).not.toContain('secret-token-123');
    expect(body).not.toContain('stack');
    expect(body).not.toContain('.ts:');
  });

  it('turns an unexpected exception into a safe 500 INTERNAL', async () => {
    failWith(new TypeError('Cannot read properties of undefined (reading x)'));
    const response = await post({ term: 'ubisoft' });

    expect(response.statusCode).toBe(500);
    expect(response.json().error).toEqual({
      code: 'INTERNAL',
      message: 'Something went wrong.',
      retryable: true,
    });
  });

  it('does not log authorization or cookie headers', async () => {
    await app.inject({
      method: 'POST',
      url: '/api/collections',
      payload: { term: 'ubisoft' },
      headers: { authorization: 'Bearer leaked-value', cookie: 'session=leaked-cookie' },
    });

    expect(logLines.join('')).not.toContain('leaked-value');
    expect(logLines.join('')).not.toContain('leaked-cookie');
  });
});

describe('GET /api/posts', () => {
  it('returns collection null for a term never collected', async () => {
    const response = await app.inject({ method: 'GET', url: '/api/posts?term=ubisoft' });

    expect(response.statusCode).toBe(200);
    expect(response.json()).toEqual({ collection: null, posts: [] });
  });

  it('returns the same posts as the last collection, from the database only', async () => {
    const collected = (await post({ term: 'ubisoft' })).json();
    clock.advanceSeconds(3600);

    const response = await app.inject({ method: 'GET', url: '/api/posts?term=r/Ubisoft' });

    expect(response.json().posts).toEqual(collected.posts);
    expect(response.json().collection.source).toBe('cache');
    expect(collector.calls).toHaveLength(1);
  });

  it.each(['/api/posts', '/api/posts?term=', '/api/posts?term=r/'])(
    'rejects %s with 400 INVALID_TERM',
    async (url) => {
      const response = await app.inject({ method: 'GET', url });
      expect(response.statusCode).toBe(400);
      expect(response.json().error.code).toBe('INVALID_TERM');
    },
  );
});
