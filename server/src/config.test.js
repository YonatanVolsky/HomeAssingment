import { describe, expect, it } from 'vitest';
import { ConfigError, loadConfig } from './config.js';

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
    const config = loadConfig({ PORT: '4000', INNER_PORT: '', INNER_TIMEOUT_MS: '50000' });
    expect(config.port).toBe(4000);
    expect(config.innerPort).toBe(3002);
    expect(config.innerTimeoutMs).toBe(50000);
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
  ])('rejects %o naming %s', (env, variable) => {
    expect(() => loadConfig(env)).toThrow(ConfigError);
    expect(() => loadConfig(env)).toThrow(new RegExp(`Invalid configuration: ${variable}`));
  });
});
