import { describe, expect, it } from 'vitest';
import { normalizeTerm } from '../../../src/collector/normalizeTerm.js';
import { AppError } from '../../../src/errors.js';

describe('normalizeTerm', () => {
  it.each([
    ['ubisoft', 'ubisoft'],
    ['r/Ubisoft', 'ubisoft'],
    ['/r/Ubisoft/', 'ubisoft'],
    ['  R/UBISOFT  ', 'ubisoft'],
    ['https://www.reddit.com/r/ubisoft/', 'ubisoft'],
    ['https://old.reddit.com/r/Ubisoft/new/?sort=new', 'ubisoft'],
    ['reddit.com/r/ubisoft', 'ubisoft'],
    ['de', 'de'],
    ['Ask_Reddit_2', 'ask_reddit_2'],
    ['a'.repeat(21), 'a'.repeat(21)],
  ])('accepts %j as %j', (input, expected) => {
    expect(normalizeTerm(input)).toBe(expected);
  });

  it.each([
    [''],
    ['   '],
    ['r/'],
    ['/r/'],
    ['a'],
    ['a'.repeat(22)],
    ['bad name!'],
    ['ubisoft crash'],
    ['r/ubi-soft'],
    ['https://example.com/r/ubisoft'],
  ])('rejects %j with INVALID_TERM', (input) => {
    expect(() => normalizeTerm(input)).toThrow(AppError);
    try {
      normalizeTerm(input);
    } catch (error) {
      expect((error as AppError).code).toBe('INVALID_TERM');
    }
  });
});
