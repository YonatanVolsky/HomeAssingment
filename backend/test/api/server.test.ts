import { mkdtempSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';
import { startServer } from '../../src/server.js';

const env = () => ({
  PORT: '0',
  DB_PATH: join(mkdtempSync(join(tmpdir(), 'server-')), 'test.db'),
  COLLECTOR_MODE: 'fixture',
  LOG_LEVEL: 'silent',
});

describe('startServer', () => {
  it('applies the schema, listens, and serves a fixture collection', async () => {
    const server = await startServer(env());
    try {
      const health = await fetch(`${server.url}/api/health`);
      expect(await health.json()).toMatchObject({ status: 'ok', collectorMode: 'fixture' });

      const collected = await fetch(`${server.url}/api/collections`, {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ term: 'ubisoft' }),
      });
      expect(((await collected.json()) as { posts: unknown[] }).posts.length).toBeGreaterThan(0);
    } finally {
      await server.close();
    }
  });

  it('keeps data across a restart on the same database file', async () => {
    const config = env();
    const first = await startServer(config);
    await fetch(`${first.url}/api/collections`, {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ term: 'ubisoft' }),
    });
    await first.close();

    const second = await startServer(config);
    try {
      const feed = (await (await fetch(`${second.url}/api/posts?term=ubisoft`)).json()) as {
        collection: unknown;
        posts: unknown[];
      };
      expect(feed.collection).toMatchObject({ term: 'ubisoft', source: 'cache' });
      expect(feed.posts.length).toBeGreaterThan(0);
    } finally {
      await second.close();
    }
  });

  it('refuses to start with a clear message on invalid configuration', async () => {
    await expect(startServer({ ...env(), PORT: 'abc' })).rejects.toThrow(
      /Invalid configuration: PORT/,
    );
  });
});
