import { describe, expect, it, vi } from 'vitest';
import { ApiError, DEFAULT_HEALTH, getFeed, getHealth } from './client';
const json = (status, body) =>
  new Response(JSON.stringify(body), { status, headers: { 'content-type': 'application/json' } });

const okBody = {
  collection: {
    id: 1,
    term: 'ubisoft',
    source: 'live',
    collectedAt: '2026-10-29T12:00:00.000Z',
    postCount: 0,
  },
  posts: [],
};

async function caught(promise) {
  try {
    await promise;
  } catch (error) {
    if (error instanceof ApiError) return error;
    throw error;
  }
  throw new Error('expected an ApiError');
}
describe('getFeed', () => {
  it('GETs the term and freshness in the query string and returns the response', async () => {
    const fetchImpl = vi.fn(async () => json(200, okBody));
    const result = await getFeed('r/ubi soft?&x', 'live', { fetchImpl });
    expect(result).toEqual(okBody);
    const [url, init] = fetchImpl.mock.calls[0];
    expect(url).toBe('/api/posts?term=r%2Fubi%20soft%3F%26x&freshness=live');
    expect(init.method).toBeUndefined();
    expect(init.body).toBeUndefined();
  });
  it('throws an ApiError carrying the server error and the last good feed', async () => {
    const fetchImpl = async () =>
      json(504, {
        error: {
          code: 'UPSTREAM_TIMEOUT',
          message: 'Reddit took too long to respond.',
          retryable: true,
        },
        lastGood: okBody,
      });
    const error = await caught(getFeed('ubisoft', 'auto', { fetchImpl }));
    expect(error.body).toEqual({
      code: 'UPSTREAM_TIMEOUT',
      message: 'Reddit took too long to respond.',
      retryable: true,
    });
    expect(error.lastGood).toEqual(okBody);
  });
  it('reports NETWORK when the backend cannot be reached', async () => {
    const fetchImpl = async () => {
      throw new TypeError('Failed to fetch');
    };
    const error = await caught(getFeed('ubisoft', 'auto', { fetchImpl }));
    expect(error.body).toEqual({
      code: 'NETWORK',
      message: 'Cannot reach the local server. Is the backend running?',
      retryable: true,
    });
  });
  it('reports NETWORK when the dev proxy answers with a non-JSON error page', async () => {
    const fetchImpl = async () => new Response('<html>proxy error</html>', { status: 500 });
    expect((await caught(getFeed('ubisoft', 'auto', { fetchImpl }))).body.code).toBe('NETWORK');
  });
  it('reports NETWORK when the request takes longer than the client timeout', async () => {
    const fetchImpl = (_url, init) =>
      new Promise((_resolve, reject) => {
        init?.signal?.addEventListener('abort', () =>
          reject(new DOMException('aborted', 'AbortError')),
        );
      });
    const error = await caught(getFeed('ubisoft', 'auto', { fetchImpl, timeoutMs: 20 }));
    expect(error.body.code).toBe('NETWORK');
  });
  it('rethrows an abort requested by the caller as an AbortError', async () => {
    const controller = new AbortController();
    const fetchImpl = (_url, init) =>
      new Promise((_resolve, reject) => {
        init?.signal?.addEventListener('abort', () =>
          reject(new DOMException('aborted', 'AbortError')),
        );
      });
    const pending = getFeed('ubisoft', 'auto', { fetchImpl, signal: controller.signal });
    controller.abort();
    await expect(pending).rejects.toMatchObject({ name: 'AbortError' });
  });
});
describe('getHealth', () => {
  it('returns the server health', async () => {
    const body = { status: 'ok', db: 'ok', collectorMode: 'fixture', staleAfterSeconds: 10 };
    expect(await getHealth({ fetchImpl: async () => json(200, body) })).toEqual(body);
  });
  it('falls back to defaults when the backend is unreachable', async () => {
    const fetchImpl = async () => {
      throw new TypeError('Failed to fetch');
    };
    expect(await getHealth({ fetchImpl })).toEqual(DEFAULT_HEALTH);
  });
});
