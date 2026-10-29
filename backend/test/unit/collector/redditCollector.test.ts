import type { ErrorCode, Post } from '@reddit-collector/contracts';
import { describe, expect, it } from 'vitest';
import {
  RedditCollector,
  type ListingSource,
  type TokenSource,
} from '../../../src/collector/redditCollector.js';
import { AppError, ERROR_TABLE } from '../../../src/errors.js';
import { makePost } from '../../helpers.js';

type Step = Post[] | Error | 'hang';

/** A listing source that plays back a script of results, one per call. */
function scriptedSource(...steps: Step[]) {
  const tokensSeen: string[] = [];
  const source: ListingSource = {
    async fetchNewPosts(_subreddit, _limit, token, signal) {
      tokensSeen.push(token);
      const step = steps.shift() ?? new Error('script exhausted');
      if (step === 'hang') {
        return new Promise<Post[]>((_resolve, reject) => {
          signal.addEventListener('abort', () => reject(signal.reason), { once: true });
        });
      }
      if (step instanceof Error) throw step;
      return step;
    },
  };
  return { source, calls: () => tokensSeen.length, tokensSeen };
}

function fakeTokens(): TokenSource & { invalidations: number } {
  let version = 1;
  return {
    invalidations: 0,
    async get() {
      return `token-${version}`;
    },
    invalidate() {
      this.invalidations += 1;
      version += 1;
    },
  };
}

function build(source: ListingSource, options: { deadlineMs?: number; tokens?: TokenSource } = {}) {
  const sleeps: number[] = [];
  const collector = new RedditCollector({
    tokens: options.tokens ?? fakeTokens(),
    source,
    deadlineMs: options.deadlineMs ?? 5000,
    random: () => 0,
    sleep: async (ms) => {
      sleeps.push(ms);
    },
  });
  return { collector, sleeps };
}

const timeout = () => Object.assign(new Error('timeout'), { code: 'UND_ERR_HEADERS_TIMEOUT' });
const reset = () => Object.assign(new Error('reset'), { code: 'ECONNRESET' });

describe('RedditCollector', () => {
  it('returns posts from the first successful attempt', async () => {
    const { source, calls } = scriptedSource([makePost('t3_a')]);
    const { collector } = build(source);

    expect(await collector.collect('ubisoft', 25)).toHaveLength(1);
    expect(calls()).toBe(1);
  });

  it('retries a network error up to 2 times with exponential backoff', async () => {
    const { source, calls } = scriptedSource(reset(), reset(), [makePost('t3_a')]);
    const { collector, sleeps } = build(source);

    expect(await collector.collect('ubisoft', 25)).toHaveLength(1);
    expect(calls()).toBe(3);
    expect(sleeps).toEqual([250, 500]);
  });

  it('retries a 5xx with the same policy', async () => {
    const { source, calls } = scriptedSource(new AppError('UPSTREAM_ERROR'), [makePost('t3_a')]);
    await build(source).collector.collect('ubisoft', 25);
    expect(calls()).toBe(2);
  });

  it('reports UPSTREAM_TIMEOUT when retries run out on timeouts', async () => {
    const { source, calls } = scriptedSource(timeout(), timeout(), timeout());

    await expect(build(source).collector.collect('ubisoft', 25)).rejects.toMatchObject({
      code: 'UPSTREAM_TIMEOUT',
    });
    expect(calls()).toBe(3);
  });

  it('reports UPSTREAM_ERROR when retries run out on other failures', async () => {
    const { source } = scriptedSource(timeout(), reset(), reset());
    await expect(build(source).collector.collect('ubisoft', 25)).rejects.toMatchObject({
      code: 'UPSTREAM_ERROR',
    });
  });

  it('refreshes the token once on an auth failure and retries with the new token', async () => {
    const tokens = fakeTokens();
    const { source, tokensSeen } = scriptedSource(new AppError('UPSTREAM_AUTH'), [
      makePost('t3_a'),
    ]);

    await build(source, { tokens }).collector.collect('ubisoft', 25);

    expect(tokens.invalidations).toBe(1);
    expect(tokensSeen).toEqual(['token-1', 'token-2']);
  });

  it('gives up with UPSTREAM_AUTH when the refreshed token is also rejected', async () => {
    const { source, calls } = scriptedSource(
      new AppError('UPSTREAM_AUTH'),
      new AppError('UPSTREAM_AUTH'),
    );
    await expect(build(source).collector.collect('ubisoft', 25)).rejects.toMatchObject({
      code: 'UPSTREAM_AUTH',
    });
    expect(calls()).toBe(2);
  });

  it('does not retry a 429 and keeps retryAfterSeconds', async () => {
    const limited = new AppError('RATE_LIMITED', undefined, { retryAfterSeconds: 12 });
    const { source, calls } = scriptedSource(limited);

    await expect(build(source).collector.collect('ubisoft', 25)).rejects.toMatchObject({
      code: 'RATE_LIMITED',
      retryAfterSeconds: 12,
    });
    expect(calls()).toBe(1);
  });

  it('does not retry an unexpected 4xx', async () => {
    const { source, calls } = scriptedSource(
      new AppError('UPSTREAM_ERROR', undefined, { autoRetry: false }),
    );
    await expect(build(source).collector.collect('ubisoft', 25)).rejects.toThrow();
    expect(calls()).toBe(1);
  });

  it('does not retry a contract error', async () => {
    const { source, calls } = scriptedSource(new AppError('CONTRACT_ERROR'));
    await expect(build(source).collector.collect('ubisoft', 25)).rejects.toMatchObject({
      code: 'CONTRACT_ERROR',
    });
    expect(calls()).toBe(1);
  });

  it('stops at the collection deadline with UPSTREAM_TIMEOUT when Reddit hangs', async () => {
    const { source } = scriptedSource('hang', 'hang', 'hang');
    const started = Date.now();

    await expect(
      build(source, { deadlineMs: 100 }).collector.collect('ubisoft', 25),
    ).rejects.toMatchObject({ code: 'UPSTREAM_TIMEOUT' });
    expect(Date.now() - started).toBeLessThan(1000);
  });

  it('skips a retry whose backoff would end after the deadline', async () => {
    const { source, calls } = scriptedSource(reset(), [makePost('t3_a')]);
    const { collector, sleeps } = build(source, { deadlineMs: 200 });

    await expect(collector.collect('ubisoft', 25)).rejects.toMatchObject({
      code: 'UPSTREAM_ERROR',
    });
    expect(calls()).toBe(1);
    expect(sleeps).toEqual([]);
  });

  it.each(Object.keys(ERROR_TABLE) as ErrorCode[])(
    'auto-retries %s exactly as the error table says',
    async (code) => {
      const { source, calls } = scriptedSource(
        new AppError(code),
        new AppError(code),
        new AppError(code),
      );
      await expect(build(source).collector.collect('ubisoft', 25)).rejects.toMatchObject({ code });

      const expected = code === 'UPSTREAM_AUTH' ? 2 : ERROR_TABLE[code].autoRetry ? 3 : 1;
      expect(calls()).toBe(expected);
    },
  );
});
