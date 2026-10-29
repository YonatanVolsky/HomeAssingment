import { describe, expect, it } from 'vitest';
import { TokenProvider, type TokenFetcher } from '../../../src/collector/tokenProvider.js';
import { AppError } from '../../../src/errors.js';
import { FakeClock, makeLogger } from '../../helpers.js';

function setup(fetcher: TokenFetcher) {
  const clock = new FakeClock();
  const { entries, logger } = makeLogger();
  return { clock, entries, tokens: new TokenProvider(fetcher, clock, logger) };
}

function countingFetcher(expiresInSeconds = 3600) {
  let calls = 0;
  const fetcher: TokenFetcher = async () => {
    calls += 1;
    return { accessToken: `token-${calls}`, expiresInSeconds };
  };
  return { fetcher, calls: () => calls };
}

const signal = new AbortController().signal;

describe('TokenProvider', () => {
  it('reuses a cached token while it is valid', async () => {
    const { fetcher, calls } = countingFetcher();
    const { tokens } = setup(fetcher);

    expect(await tokens.get(signal)).toBe('token-1');
    expect(await tokens.get(signal)).toBe('token-1');
    expect(calls()).toBe(1);
  });

  it('refreshes 60 seconds before expiry', async () => {
    const { fetcher } = countingFetcher(3600);
    const { tokens, clock } = setup(fetcher);
    await tokens.get(signal);

    clock.advanceSeconds(3539);
    expect(await tokens.get(signal)).toBe('token-1');
    clock.advanceSeconds(1);
    expect(await tokens.get(signal)).toBe('token-2');
  });

  it('shares one refresh between concurrent callers', async () => {
    const { fetcher, calls } = countingFetcher();
    const { tokens } = setup(fetcher);

    const results = await Promise.all([tokens.get(signal), tokens.get(signal), tokens.get(signal)]);

    expect(results).toEqual(['token-1', 'token-1', 'token-1']);
    expect(calls()).toBe(1);
  });

  it('fetches a new token after invalidate()', async () => {
    const { fetcher } = countingFetcher();
    const { tokens } = setup(fetcher);
    const first = await tokens.get(signal);

    tokens.invalidate(first);

    expect(await tokens.get(signal)).toBe('token-2');
  });

  it('turns a failed fetch into UPSTREAM_AUTH and does not cache the failure', async () => {
    let fail = true;
    const { tokens } = setup(async () => {
      if (fail) throw new Error('HTTP 500 from token endpoint');
      return { accessToken: 'recovered', expiresInSeconds: 3600 };
    });

    await expect(tokens.get(signal)).rejects.toMatchObject({ code: 'UPSTREAM_AUTH' });
    fail = false;
    expect(await tokens.get(signal)).toBe('recovered');
  });

  it.each(['UPSTREAM_TIMEOUT', 'RATE_LIMITED'] as const)(
    'lets %s through instead of calling it an auth failure',
    async (code) => {
      const { tokens } = setup(async () => {
        throw new AppError(code);
      });
      await expect(tokens.get(signal)).rejects.toMatchObject({ code });
    },
  );

  it('never logs the token value', async () => {
    const { fetcher } = countingFetcher();
    const { tokens, entries } = setup(fetcher);
    await tokens.get(signal);

    expect(JSON.stringify(entries)).not.toContain('token-1');
    expect(entries.some((e) => e.msg.includes('token refreshed'))).toBe(true);
  });
});

describe('TokenProvider with concurrent collections', () => {
  it("does not fail other callers when the first caller's deadline aborts the shared refresh", async () => {
    let finish!: (token: { accessToken: string; expiresInSeconds: number }) => void;
    let fetchSignal: AbortSignal | undefined;
    const { tokens } = setup((signal) => {
      fetchSignal = signal;
      return new Promise((resolve) => {
        finish = resolve;
      });
    });
    const first = new AbortController();
    const second = new AbortController();

    const a = tokens.get(first.signal);
    const b = tokens.get(second.signal);
    first.abort(new AppError('UPSTREAM_TIMEOUT'));

    await expect(a).rejects.toMatchObject({ code: 'UPSTREAM_TIMEOUT' });
    expect(fetchSignal?.aborted).toBe(false);
    finish({ accessToken: 'shared', expiresInSeconds: 3600 });
    expect(await b).toBe('shared');
  });

  it('keeps a newer token when a caller invalidates the token it was rejected with', async () => {
    const { fetcher } = countingFetcher();
    const { tokens } = setup(fetcher);
    const stale = await tokens.get(signal);
    tokens.invalidate(stale);
    const fresh = await tokens.get(signal);

    tokens.invalidate(stale);

    expect(fresh).toBe('token-2');
    expect(await tokens.get(signal)).toBe('token-2');
  });
});
