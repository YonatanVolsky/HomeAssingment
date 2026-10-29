import { describe, expect, it } from 'vitest';
import {
  mapAuthor,
  mapFlair,
  toAbsolutePermalink,
  toIsoUtc,
  truncatePreview,
} from '../../../src/collector/mappers.js';

const expectContractError = (fn: () => unknown) => {
  expect(fn).toThrow(expect.objectContaining({ code: 'CONTRACT_ERROR' }));
};

describe('toIsoUtc', () => {
  it.each([
    [1730000000, 'epoch seconds'],
    [1730000000000, 'epoch milliseconds'],
    [1730000000.5, 'fractional epoch seconds'],
    ['2024-10-27T03:33:20Z', 'ISO string'],
    ['2024-10-27T05:33:20+02:00', 'ISO string with offset'],
  ])('converts %j (%s) to ISO UTC', (value) => {
    expect(toIsoUtc(value)).toMatch(/^2024-10-27T03:33:20(\.\d{3})?Z$/);
  });

  it.each([['not a date'], [null], [undefined], [Number.NaN], [-1], [{}]])(
    'rejects %j with CONTRACT_ERROR',
    (value) => expectContractError(() => toIsoUtc(value)),
  );
});

describe('toAbsolutePermalink', () => {
  it('prefixes a relative permalink with https://www.reddit.com', () => {
    expect(toAbsolutePermalink('/r/ubisoft/comments/abc/title/')).toBe(
      'https://www.reddit.com/r/ubisoft/comments/abc/title/',
    );
  });

  it('forces https and drops query and fragment on an absolute reddit URL', () => {
    expect(
      toAbsolutePermalink('http://old.reddit.com/r/ubisoft/comments/abc/?utm_source=share#x'),
    ).toBe('https://old.reddit.com/r/ubisoft/comments/abc/');
  });

  it.each([
    ['https://evil.com/r/ubisoft/comments/abc/'],
    ['https://reddit.com.evil.com/r/x/'],
    ['javascript:alert(1)'],
    [''],
    [42],
  ])('rejects %j with CONTRACT_ERROR', (value) =>
    expectContractError(() => toAbsolutePermalink(value)),
  );
});

describe('truncatePreview', () => {
  it.each([[null], [undefined], [''], ['   \n\t ']])('returns null for %j', (value) => {
    expect(truncatePreview(value)).toBeNull();
  });

  it('collapses whitespace', () => {
    expect(truncatePreview('Hello\n\n  world\t!')).toBe('Hello world !');
  });

  it('removes common markdown and HTML noise', () => {
    expect(
      truncatePreview(
        '# Title\n> quoted **bold** _it_ [link](https://x.y) <b>tag</b> &amp; &#x200B;',
      ),
    ).toBe('Title quoted bold it link tag &');
  });

  it('truncates long text to at most 300 characters on a word boundary with an ellipsis', () => {
    const preview = truncatePreview('word '.repeat(100))!;

    expect(preview.length).toBeLessThanOrEqual(300);
    expect(preview.endsWith('word…')).toBe(true);
  });

  it('leaves text of exactly 300 characters untouched', () => {
    const text = 'a'.repeat(300);
    expect(truncatePreview(text)).toBe(text);
  });
});

describe('mapAuthor', () => {
  it.each([['[deleted]'], ['[removed]'], [''], [null], [undefined]])('maps %j to null', (v) => {
    expect(mapAuthor(v)).toBeNull();
  });

  it('keeps a real username', () => {
    expect(mapAuthor('LazyGas7003')).toBe('LazyGas7003');
  });
});

describe('mapFlair', () => {
  it('trims flair text and maps empty to null', () => {
    expect(mapFlair('  Question ')).toBe('Question');
    expect(mapFlair('  ')).toBeNull();
    expect(mapFlair(null)).toBeNull();
  });
});
