import { describe, expect, it } from 'vitest';
import { loadConfig } from '../../src/config.js';

describe('loadConfig', () => {
  it('applies defaults when the environment is empty', () => {
    const config = loadConfig({});

    expect(config).toMatchObject({
      port: 3001,
      host: '127.0.0.1',
      collectorMode: 'live',
      dbPath: './data/collector.db',
      maxPosts: 25,
      collectionTtlSeconds: 60,
      staleAfterSeconds: 600,
      requestTimeoutMs: 8000,
      collectionDeadlineMs: 25000,
      logLevel: 'info',
    });
  });

  it('uses a separate database file in fixture mode', () => {
    expect(loadConfig({ COLLECTOR_MODE: 'fixture' }).dbPath).toBe('./data/fixture.db');
  });

  it('lets an explicit DB_PATH win over the fixture default', () => {
    const config = loadConfig({ COLLECTOR_MODE: 'fixture', DB_PATH: '/tmp/x.db' });
    expect(config.dbPath).toBe('/tmp/x.db');
  });

  it('parses numeric values from strings', () => {
    expect(loadConfig({ PORT: '4000', COLLECTION_TTL_SECONDS: '0' })).toMatchObject({
      port: 4000,
      collectionTtlSeconds: 0,
    });
  });

  it('rejects an out-of-range port with a message naming the variable', () => {
    expect(() => loadConfig({ PORT: '70000' })).toThrow(/PORT/);
  });

  it('rejects an unknown collector mode', () => {
    expect(() => loadConfig({ COLLECTOR_MODE: 'browser' })).toThrow(/COLLECTOR_MODE/);
  });

  it('rejects a per-request timeout that is not below the collection deadline', () => {
    expect(() =>
      loadConfig({ REQUEST_TIMEOUT_MS: '20000', COLLECTION_DEADLINE_MS: '20000' }),
    ).toThrow(/REQUEST_TIMEOUT_MS/);
  });

  it('returns a frozen object', () => {
    expect(Object.isFrozen(loadConfig({}))).toBe(true);
  });
});
