import { describe, expect, it } from 'vitest';
import { ROUTE_NAMES, ROUTE_PRESETS } from './routes.js';

const route = (path) => ROUTE_PRESETS.rest.find((r) => r.path === path);

describe('rest routes', () => {
  it('lists the preset names', () => {
    expect(ROUTE_NAMES).toEqual(['rest']);
  });

  it('posts builds the GET posts command', () => {
    expect(route('/api/posts').toMessage({ term: 'r/x', freshness: 'live' })).toEqual({
      v: 1,
      command: 'GET',
      resource: 'posts',
      args: { term: 'r/x', freshness: 'live' },
    });
  });

  it('omits absent values but keeps empty ones', () => {
    expect(route('/api/posts').toMessage({}).args).toEqual({});
    expect(route('/api/posts').toMessage({ term: '' }).args).toEqual({ term: '' });
  });

  it('takes the first of repeated values', () => {
    expect(route('/api/posts').toMessage({ term: ['a', 'b'] }).args.term).toBe('a');
  });

  it('health builds the health command', () => {
    expect(route('/api/health').toMessage({})).toEqual({
      v: 1,
      command: 'GET',
      resource: 'health',
    });
  });

  it('presets cannot be changed at runtime', () => {
    expect(Object.isFrozen(ROUTE_PRESETS)).toBe(true);
    expect(Object.isFrozen(ROUTE_PRESETS.rest)).toBe(true);
  });
});
