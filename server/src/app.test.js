import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import request from 'supertest';
import { describe, expect, it, vi } from 'vitest';
import { createApp } from './app.js';
import { errorBody, InnerError } from './errors.js';
import { ROUTE_PRESETS } from './routes.js';

const result = { collection: { id: 1, term: 'ubisoft' }, posts: [] };

function appWith(send, staticDir) {
  const inner = { send: vi.fn(send) };
  return { app: createApp({ routes: ROUTE_PRESETS.rest, inner, staticDir }), inner };
}

describe('API routes', () => {
  it('GET /api/posts sends the command and returns the result', async () => {
    const { app, inner } = appWith(async () => ({ ok: true, result }));
    const response = await request(app).get('/api/posts?term=r%2FUbisoft&freshness=live');
    expect(inner.send).toHaveBeenCalledWith({
      v: 1,
      command: 'GET',
      resource: 'posts',
      args: { term: 'r/Ubisoft', freshness: 'live' },
    });
    expect(response.status).toBe(200);
    expect(response.body).toEqual(result);
    expect(response.headers['cache-control']).toBe('no-store');
  });

  it('an encoded term reaches the inner server unchanged', async () => {
    const { app, inner } = appWith(async () => ({ ok: true, result }));
    await request(app).get('/api/posts?term=r%2Fubisoft%3Fx%3D1%26freshness%3Dlive&freshness=auto');
    expect(inner.send.mock.calls[0][0].args).toEqual({
      term: 'r/ubisoft?x=1&freshness=live',
      freshness: 'auto',
    });
  });

  it('error replies map to status, body and Retry-After', async () => {
    const error = { code: 'RATE_LIMITED', message: 'm', retryable: true, retryAfterSeconds: 30 };
    const { app } = appWith(async () => ({ ok: false, error, lastGood: { x: 1 } }));
    const response = await request(app).get('/api/posts?term=ubisoft');
    expect(response.status).toBe(429);
    expect(response.body).toEqual({ error, lastGood: { x: 1 } });
    expect(response.headers['retry-after']).toBe('30');
  });

  it.each([
    ['NOT_FOUND_SUBREDDIT', 404],
    ['INVALID_TERM', 400],
  ])('%s maps to %i without lastGood', async (code, status) => {
    const error = { code, message: 'm', retryable: false };
    const { app } = appWith(async () => ({ ok: false, error }));
    const response = await request(app).get('/api/posts?term=x');
    expect(response.status).toBe(status);
    expect(response.body).toEqual({ error });
    expect(response.headers['retry-after']).toBeUndefined();
  });

  it.each([
    ['INNER_UNAVAILABLE', 503],
    ['UPSTREAM_TIMEOUT', 504],
  ])('a transport error %s maps to %i', async (code, status) => {
    const { app } = appWith(async () => {
      throw new InnerError(code);
    });
    const response = await request(app).get('/api/posts?term=x');
    expect(response.status).toBe(status);
    expect(response.body).toEqual({ error: errorBody(code) });
  });

  it('an unexpected exception is a safe 500', async () => {
    const { app } = appWith(async () => {
      throw new Error('secret');
    });
    const response = await request(app).get('/api/posts?term=x');
    expect(response.status).toBe(500);
    expect(response.body).toEqual({ error: errorBody('INTERNAL') });
    expect(response.text).not.toContain('secret');
  });

  it('GET /api/health with the inner server down is 503', async () => {
    const { app } = appWith(async () => {
      throw new InnerError('INNER_UNAVAILABLE');
    });
    const response = await request(app).get('/api/health');
    expect(response.status).toBe(503);
    expect(response.body.error.code).toBe('INNER_UNAVAILABLE');
  });

  it('unknown API paths and methods are JSON 404s', async () => {
    const { app, inner } = appWith(async () => ({ ok: true, result }));
    for (const response of [
      await request(app).get('/api/nope'),
      await request(app).post('/api/posts'),
    ]) {
      expect(response.status).toBe(404);
      expect(response.body).toEqual({ error: errorBody('NOT_FOUND') });
      expect(response.headers['cache-control']).toBe('no-store');
    }
    expect(inner.send).not.toHaveBeenCalled();
  });
});

describe('static UI', () => {
  function dist() {
    const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'dist-'));
    fs.writeFileSync(path.join(dir, 'index.html'), '<title>UI</title>');
    fs.writeFileSync(path.join(dir, 'app.js'), 'console.log(1)');
    return dir;
  }

  it('serves files and falls back to index.html for client routes', async () => {
    const { app } = appWith(async () => ({ ok: true, result }), dist());
    expect((await request(app).get('/')).text).toContain('<title>UI</title>');
    expect((await request(app).get('/some/page')).text).toContain('<title>UI</title>');
    expect((await request(app).get('/app.js')).text).toBe('console.log(1)');
  });

  it.each([
    '/..%2fsecret.txt',
    '/%2e%2e/secret.txt',
    '/%2e%2e%2fsecret.txt',
    '/assets/..%2f..%2fsecret.txt',
  ])('never serves a file outside the build folder: %s', async (url) => {
    // A sentinel next to the build folder: reachable only through an escape.
    const root = fs.mkdtempSync(path.join(os.tmpdir(), 'ui-'));
    fs.writeFileSync(path.join(root, 'secret.txt'), 'SENTINEL-OUTSIDE-DIST');
    const dir = path.join(root, 'dist');
    fs.mkdirSync(dir);
    fs.writeFileSync(path.join(dir, 'index.html'), '<title>UI</title>');
    const { app } = appWith(async () => ({ ok: true, result }), dir);
    const response = await request(app).get(url);
    expect(response.text).not.toContain('SENTINEL-OUTSIDE-DIST');
  });

  it('a malformed URL gets a plain error, never a stack trace', async () => {
    const { app } = appWith(async () => ({ ok: true, result }), dist());
    const response = await request(app).get('/%E0');
    expect(response.status).toBe(400);
    expect(response.body).toEqual({ error: errorBody('INVALID_REQUEST') });
    expect(response.text).not.toMatch(/URIError|node_modules|at /);
  });

  it('serves no UI when there is no build', async () => {
    const { app } = appWith(async () => ({ ok: true, result }), undefined);
    expect((await request(app).get('/')).status).toBe(404);
  });
});
