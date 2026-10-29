import { mkdtempSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';
import { buildApp } from '../../src/app.js';
import { loadConfig } from '../../src/config.js';
import { FakeClock } from '../helpers.js';
import { FakeCollector, memoryRepository } from '../fakes.js';

async function appWithStatic(staticDir: string | undefined) {
  const clock = new FakeClock();
  return buildApp({
    repository: memoryRepository(clock).repository,
    collector: new FakeCollector(),
    clock,
    config: loadConfig({}),
    staticDir,
  });
}

describe('static frontend serving', () => {
  const dir = mkdtempSync(join(tmpdir(), 'dist-'));
  writeFileSync(join(dir, 'index.html'), '<!doctype html><title>Reddit collector</title>');

  it('serves index.html at / when the build exists', async () => {
    const app = await appWithStatic(dir);
    const response = await app.inject({ method: 'GET', url: '/' });

    expect(response.statusCode).toBe(200);
    expect(response.body).toContain('Reddit collector');
    await app.close();
  });

  it('falls back to index.html for client-side routes', async () => {
    const app = await appWithStatic(dir);
    expect((await app.inject({ method: 'GET', url: '/some/page' })).body).toContain('<title>');
    await app.close();
  });

  it('answers unknown API routes with a JSON 404, not the page', async () => {
    const app = await appWithStatic(dir);
    const response = await app.inject({ method: 'GET', url: '/api/nope' });

    expect(response.statusCode).toBe(404);
    expect(response.json()).toEqual({ message: 'Not found' });
    await app.close();
  });

  it('starts without static serving when the build is missing', async () => {
    const app = await appWithStatic(join(dir, 'missing'));
    expect((await app.inject({ method: 'GET', url: '/' })).statusCode).toBe(404);
    await app.close();
  });
});
