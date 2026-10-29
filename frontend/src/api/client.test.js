import { describe, expect, it, vi } from 'vitest';
import { ApiError, collect, DEFAULT_HEALTH, getHealth, getPosts } from './client';
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
describe('collect', () => {
  it('POSTs the term and force flag as JSON and returns the response', async () => {
    const fetchImpl = vi.fn(async () => json(200, okBody));
    const result = await collect('r/ubisoft', true, { fetchImpl });
    expect(result).toEqual(okBody);
    expect(fetchImpl).toHaveBeenCalledWith(
      '/api/collections',
      expect.objectContaining({
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ term: 'r/ubisoft', force: true }),
      }),
    );
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
    const error = await caught(collect('ubisoft', false, { fetchImpl }));
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
    const error = await caught(collect('ubisoft', false, { fetchImpl }));
    expect(error.body).toEqual({
      code: 'NETWORK',
      message: 'Cannot reach the local server. Is the backend running?',
      retryable: true,
    });
  });
  it('reports NETWORK when the dev proxy answers with a non-JSON error page', async () => {
    const fetchImpl = async () => new Response('<html>proxy error</html>', { status: 500 });
    expect((await caught(collect('ubisoft', false, { fetchImpl }))).body.code).toBe('NETWORK');
  });
  it('reports NETWORK when the request takes longer than the client timeout', async () => {
    const fetchImpl = (_url, init) =>
      new Promise((_resolve, reject) => {
        init?.signal?.addEventListener('abort', () =>
          reject(new DOMException('aborted', 'AbortError')),
        );
      });
    const error = await caught(collect('ubisoft', false, { fetchImpl, timeoutMs: 20 }));
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
    const pending = collect('ubisoft', false, { fetchImpl, signal: controller.signal });
    controller.abort();
    await expect(pending).rejects.toMatchObject({ name: 'AbortError' });
  });
});
describe('getPosts', () => {
  it('encodes the term in the query string', async () => {
    const fetchImpl = vi.fn(async () => json(200, { collection: null, posts: [] }));
    await getPosts('r/ubisoft', { fetchImpl });
    expect(fetchImpl).toHaveBeenCalledWith('/api/posts?term=r%2Fubisoft', expect.anything());
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
