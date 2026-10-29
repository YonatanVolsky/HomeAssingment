import { mkdtempSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import type { CollectionResponse, ErrorResponse } from '@reddit-collector/contracts';
import { describe, expect, it } from 'vitest';
import { buildApp } from '../../src/app.js';
import { DEFAULT_SAMPLE_FILE, FixtureCollector } from '../../src/collector/fixtureCollector.js';
import type { Collector } from '../../src/collector/types.js';
import { loadConfig } from '../../src/config.js';
import { openDatabase } from '../../src/db/connection.js';
import { createRepository } from '../../src/db/repository.js';
import { ensureSchema } from '../../src/db/schema.js';
import { AppError } from '../../src/errors.js';
import { FakeClock, makeLogger } from '../helpers.js';

const clock = new FakeClock();

/** One app instance on a real database file, like a server process. */
async function open(path: string, collector: Collector) {
  const db = openDatabase(path);
  ensureSchema(db);
  const app = await buildApp({
    repository: createRepository(db, clock, makeLogger().logger),
    collector,
    clock,
    config: loadConfig({ COLLECTION_TTL_SECONDS: '60' }),
  });
  return {
    app,
    db,
    close: async () => {
      await app.close();
      db.close();
    },
  };
}

const tempDb = () => join(mkdtempSync(join(tmpdir(), 'integration-')), 'collector.db');
const fixtures = () => FixtureCollector.fromFile(DEFAULT_SAMPLE_FILE, clock);

describe('persistence', () => {
  it('serves the same feed after a restart on the same file', async () => {
    const path = tempDb();
    const first = await open(path, fixtures());
    const collected = (
      await first.app.inject({
        method: 'POST',
        url: '/api/collections',
        payload: { term: 'ubisoft' },
      })
    ).json<CollectionResponse>();
    await first.close();

    const second = await open(path, fixtures());
    const read = (
      await second.app.inject({ method: 'GET', url: '/api/posts?term=ubisoft' })
    ).json<CollectionResponse>();
    await second.close();

    expect(read.posts).toEqual(collected.posts);
    expect(read.collection).toMatchObject({ id: collected.collection?.id, source: 'cache' });
  });

  it('never duplicates posts when the same term is collected again', async () => {
    const instance = await open(tempDb(), fixtures());
    const collect = () =>
      instance.app.inject({
        method: 'POST',
        url: '/api/collections',
        payload: { term: 'ubisoft', force: true },
      });

    const first = (await collect()).json<CollectionResponse>();
    await collect();
    const counts = instance.db
      .prepare(
        `SELECT (SELECT COUNT(*) FROM posts) AS posts,
                (SELECT COUNT(*) FROM collections) AS runs`,
      )
      .get();
    await instance.close();

    expect(counts).toEqual({ posts: first.posts.length, runs: 2 });
  });
});

describe('failure path', () => {
  it('stores the failed run and returns the last good feed', async () => {
    const path = tempDb();
    const good = await open(path, fixtures());
    await good.app.inject({
      method: 'POST',
      url: '/api/collections',
      payload: { term: 'ubisoft' },
    });
    await good.close();

    const failing = await open(path, {
      collect: async () => {
        throw new AppError('UPSTREAM_TIMEOUT');
      },
    });
    const response = await failing.app.inject({
      method: 'POST',
      url: '/api/collections',
      payload: { term: 'ubisoft', force: true },
    });
    const statuses = failing.db
      .prepare('SELECT status, error_code FROM collections ORDER BY id')
      .all();
    await failing.close();

    expect(response.statusCode).toBe(504);
    expect(response.json<ErrorResponse>().lastGood?.posts.length).toBeGreaterThan(0);
    expect(statuses).toEqual([
      { status: 'success', error_code: null },
      { status: 'failed', error_code: 'UPSTREAM_TIMEOUT' },
    ]);
  });
});
