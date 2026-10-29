import { describe, expect, it } from 'vitest';
import type { ErrorCode } from '@reddit-collector/contracts';
import { AppError, ERROR_TABLE, toErrorBody } from '../../src/errors.js';

const ALL_CODES = Object.keys(ERROR_TABLE) as ErrorCode[];

describe('AppError', () => {
  it('derives HTTP status and retryable from the code', () => {
    const error = new AppError('NOT_FOUND_SUBREDDIT', 'r/x was not found');

    expect(error.httpStatus).toBe(404);
    expect(error.retryable).toBe(false);
  });

  it('keeps retryAfterSeconds for rate limiting', () => {
    const error = new AppError('RATE_LIMITED', 'slow down', { retryAfterSeconds: 30 });
    expect(error.retryAfterSeconds).toBe(30);
  });

  it('falls back to the default message of the code', () => {
    expect(new AppError('UPSTREAM_TIMEOUT').message).toBe('Reddit took too long to respond.');
  });
});

describe('ERROR_TABLE', () => {
  it.each([
    ['INVALID_TERM', 400, false, false],
    ['RATE_LIMITED', 429, false, true],
    ['UPSTREAM_AUTH', 502, false, true],
    ['UPSTREAM_ERROR', 502, true, true],
    ['UPSTREAM_TIMEOUT', 504, true, true],
    ['NOT_FOUND_SUBREDDIT', 404, false, false],
    ['CONTRACT_ERROR', 502, false, true],
    ['DB_ERROR', 500, false, true],
    ['INTERNAL', 500, false, true],
  ] as const)('%s → HTTP %i, autoRetry %s, retryable %s', (code, http, autoRetry, retryable) => {
    expect(ERROR_TABLE[code]).toMatchObject({ httpStatus: http, autoRetry, retryable });
  });

  it('covers every error code exactly once', () => {
    expect(ALL_CODES).toHaveLength(9);
  });
});

describe('toErrorBody', () => {
  it('never includes the cause or a stack trace', () => {
    const cause = new Error('Authorization: Bearer secret-token');
    const body = toErrorBody(new AppError('UPSTREAM_AUTH', undefined, { cause }));

    expect(JSON.stringify(body)).not.toContain('secret-token');
    expect(body).toEqual({
      code: 'UPSTREAM_AUTH',
      message: 'Could not authenticate with Reddit.',
      retryable: true,
    });
  });

  it('includes retryAfterSeconds only when present', () => {
    const body = toErrorBody(new AppError('RATE_LIMITED', undefined, { retryAfterSeconds: 12 }));
    expect(body.retryAfterSeconds).toBe(12);
    expect(body.message).toContain('12 seconds');
  });
});

describe('autoRetry', () => {
  it('follows the table by default', () => {
    expect(new AppError('UPSTREAM_ERROR').autoRetry).toBe(true);
    expect(new AppError('RATE_LIMITED').autoRetry).toBe(false);
  });

  it('can be switched off for one error without changing what the UI is told', () => {
    const error = new AppError('UPSTREAM_ERROR', undefined, { autoRetry: false });

    expect(error.autoRetry).toBe(false);
    expect(error.retryable).toBe(true);
  });
});
