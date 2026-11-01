import { describe, expect, it } from 'vitest';
import { CLIENT_TIMEOUT_MS } from '../../frontend/src/api/client.js';
import { BROWSER_TIMEOUT_MS, ConfigError, loadConfig } from './config.js';

describe('loadConfig', () => {
  it('applies defaults', () => {
    expect(loadConfig({})).toEqual({
      port: 3001,
      host: '127.0.0.1',
      innerHost: '127.0.0.1',
      innerPort: 3002,
      apiRoutes: 'rest',
      innerTimeoutMs: 35000,
    });
  });

  it('parses numbers and treats empty strings as unset', () => {
    const config = loadConfig({ PORT: '4000', INNER_PORT: '', INNER_TIMEOUT_MS: '38000' });
    expect(config.port).toBe(4000);
    expect(config.innerPort).toBe(3002);
    expect(config.innerTimeoutMs).toBe(38000);
  });

  it('accepts port 0', () => {
    expect(loadConfig({ PORT: '0' }).port).toBe(0);
  });

  it.each([
    [{ PORT: '70000' }, 'PORT'],
    [{ PORT: 'abc' }, 'PORT'],
    [{ PORT: '3.5' }, 'PORT'],
    [{ INNER_PORT: '-1' }, 'INNER_PORT'],
    [{ INNER_TIMEOUT_MS: '999' }, 'INNER_TIMEOUT_MS'],
    [{ API_ROUTES: 'nope' }, 'API_ROUTES'],
    [{ HOST: '   ' }, 'HOST'],
    [{ COLLECTION_DEADLINE_MS: 'soon' }, 'COLLECTION_DEADLINE_MS'],
  ])('rejects %o naming %s', (env, variable) => {
    expect(() => loadConfig(env)).toThrow(ConfigError);
    expect(() => loadConfig(env)).toThrow(new RegExp(`Invalid configuration: ${variable}`));
  });
});

describe('timeout order: collector limit < INNER_TIMEOUT_MS < browser limit', () => {
  it('rejects a wait that ends before the collector gives up', () => {
    expect(() => loadConfig({ INNER_TIMEOUT_MS: '30000' })).toThrow(
      'Invalid configuration: INNER_TIMEOUT_MS: must be above 30000',
    );
  });

  it('follows the collection deadline the collector reads from the same environment', () => {
    expect(() => loadConfig({ COLLECTION_DEADLINE_MS: '32000' })).toThrow(
      'Invalid configuration: INNER_TIMEOUT_MS: must be above 37000',
    );
    expect(
      loadConfig({ COLLECTION_DEADLINE_MS: '20000', INNER_TIMEOUT_MS: '26000' }).innerTimeoutMs,
    ).toBe(26000);
  });

  it('rejects a wait the browser would not sit through', () => {
    expect(() => loadConfig({ INNER_TIMEOUT_MS: '40000' })).toThrow(
      'Invalid configuration: INNER_TIMEOUT_MS: must be below 40000',
    );
  });

  it('uses the same browser limit as the frontend', () => {
    expect(BROWSER_TIMEOUT_MS).toBe(CLIENT_TIMEOUT_MS);
  });
});
