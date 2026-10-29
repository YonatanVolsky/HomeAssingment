import { describe, expect, it } from 'vitest';
import { classifyNetworkError, classifyStatus } from '../../../src/collector/classify.js';
import { AppError } from '../../../src/errors.js';

describe('classifyStatus', () => {
  it.each([200, 204, 299])('returns null for success status %i', (status) => {
    expect(classifyStatus(status, {})).toBeNull();
  });

  it.each([401, 403])('maps %i to UPSTREAM_AUTH', (status) => {
    expect(classifyStatus(status, {})?.code).toBe('UPSTREAM_AUTH');
  });

  it('maps 404 to NOT_FOUND_SUBREDDIT', () => {
    expect(classifyStatus(404, {})?.code).toBe('NOT_FOUND_SUBREDDIT');
  });

  it('maps 429 to RATE_LIMITED using Retry-After seconds', () => {
    const error = classifyStatus(429, { 'retry-after': '17' });
    expect(error).toMatchObject({ code: 'RATE_LIMITED', retryAfterSeconds: 17, autoRetry: false });
  });

  it("falls back to Reddit's x-ratelimit-reset header", () => {
    expect(classifyStatus(429, { 'x-ratelimit-reset': '42.0' })?.retryAfterSeconds).toBe(42);
  });

  it('defaults Retry-After to 30 seconds', () => {
    expect(classifyStatus(429, {})?.retryAfterSeconds).toBe(30);
  });

  it.each([500, 502, 503])('maps %i to an auto-retried UPSTREAM_ERROR', (status) => {
    expect(classifyStatus(status, {})).toMatchObject({ code: 'UPSTREAM_ERROR', autoRetry: true });
  });

  it.each([400, 405, 418])('maps unexpected %i to UPSTREAM_ERROR without auto-retry', (status) => {
    expect(classifyStatus(status, {})).toMatchObject({ code: 'UPSTREAM_ERROR', autoRetry: false });
  });
});

describe('classifyNetworkError', () => {
  it.each(['UND_ERR_CONNECT_TIMEOUT', 'UND_ERR_HEADERS_TIMEOUT', 'UND_ERR_BODY_TIMEOUT'])(
    'maps undici %s to an auto-retried UPSTREAM_TIMEOUT',
    (code) => {
      const error = classifyNetworkError(Object.assign(new Error('t'), { code }));
      expect(error).toMatchObject({ code: 'UPSTREAM_TIMEOUT', autoRetry: true });
    },
  );

  it.each(['ECONNRESET', 'ENOTFOUND', 'ECONNREFUSED', 'UND_ERR_SOCKET'])(
    'maps %s to an auto-retried UPSTREAM_ERROR',
    (code) => {
      const error = classifyNetworkError(Object.assign(new Error('n'), { code }));
      expect(error).toMatchObject({ code: 'UPSTREAM_ERROR', autoRetry: true });
    },
  );

  it('passes an AppError through unchanged', () => {
    const original = new AppError('CONTRACT_ERROR');
    expect(classifyNetworkError(original)).toBe(original);
  });

  it('keeps the original error only as the cause', () => {
    const cause = Object.assign(new Error('socket hang up'), { code: 'ECONNRESET' });
    const error = classifyNetworkError(cause);

    expect(error.cause).toBe(cause);
    expect(error.message).not.toContain('socket');
  });
});
