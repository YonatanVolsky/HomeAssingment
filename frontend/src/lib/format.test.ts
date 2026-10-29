import { describe, expect, it } from 'vitest';
import { formatCount, isSafeRedditUrl, relativeTime } from './format';

const now = new Date('2026-10-29T12:00:00.000Z');
const ago = (seconds: number) => new Date(now.getTime() - seconds * 1000).toISOString();

describe('relativeTime', () => {
  it.each([
    [0, 'just now'],
    [44, 'just now'],
    [45, '1 min ago'],
    [49 * 60, '49 min ago'],
    [3 * 3600, '3 h ago'],
    [2 * 86400, '2 d ago'],
    [29 * 86400, '29 d ago'],
  ])('describes %i seconds ago as %j', (seconds, expected) => {
    expect(relativeTime(ago(seconds), now)).toBe(expected);
  });

  it('shows a date after 30 days', () => {
    expect(relativeTime('2026-08-01T10:00:00.000Z', now)).toBe('Aug 1, 2026');
  });

  it('treats a time slightly in the future (clock skew) as just now', () => {
    expect(relativeTime(ago(-30), now)).toBe('just now');
  });
});

describe('formatCount', () => {
  it.each([
    [0, '0'],
    [999, '999'],
    [1000, '1k'],
    [1234, '1.2k'],
    [15_600, '15.6k'],
    [1_250_000, '1.3M'],
    [-4, '-4'],
    [-1500, '-1.5k'],
  ])('formats %i as %j', (value, expected) => {
    expect(formatCount(value)).toBe(expected);
  });
});

describe('isSafeRedditUrl', () => {
  it.each([
    'https://www.reddit.com/r/ubisoft/comments/abc/',
    'https://reddit.com/r/x/',
    'https://old.reddit.com/r/x/',
  ])('accepts %s', (url) => {
    expect(isSafeRedditUrl(url)).toBe(true);
  });

  it.each([
    'http://www.reddit.com/r/x/',
    'javascript:alert(1)',
    'https://evil.com/r/x/',
    'https://reddit.com.evil.com/',
    'https://notreddit.com/',
    '/r/x/comments/abc/',
    '',
  ])('rejects %j', (url) => {
    expect(isSafeRedditUrl(url)).toBe(false);
  });
});
