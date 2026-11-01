import { describe, expect, it } from 'vitest';
import { errorBody, InnerError, statusFor } from './errors.js';

describe('statusFor', () => {
  it.each([
    ['INVALID_TERM', 400],
    ['INVALID_REQUEST', 400],
    ['NOT_FOUND_SUBREDDIT', 404],
    ['NOT_FOUND', 404],
    ['RATE_LIMITED', 429],
    ['DB_ERROR', 500],
    ['INTERNAL', 500],
    ['UPSTREAM_AUTH', 502],
    ['UPSTREAM_ERROR', 502],
    ['CONTRACT_ERROR', 502],
    ['INNER_UNAVAILABLE', 503],
    ['BUSY', 503],
    ['UPSTREAM_TIMEOUT', 504],
    ['SOMETHING_NEW', 500],
  ])('%s is %i', (code, status) => {
    expect(statusFor(code)).toBe(status);
  });
});

describe('errorBody', () => {
  it.each([
    ['INNER_UNAVAILABLE', 'The collector service is not running.', true],
    ['UPSTREAM_TIMEOUT', 'The collector took too long to respond.', true],
    ['INTERNAL', 'Something went wrong.', true],
    ['NOT_FOUND', 'Not found.', false],
    ['INVALID_REQUEST', 'The request is not valid.', false],
  ])('%s', (code, message, retryable) => {
    expect(errorBody(code)).toEqual({ code, message, retryable });
  });
});

describe('InnerError', () => {
  it('carries its code', () => {
    const error = new InnerError('INNER_UNAVAILABLE');
    expect(error).toBeInstanceOf(Error);
    expect(error.code).toBe('INNER_UNAVAILABLE');
  });
});
