// Environment configuration for the web service, read once at startup.
import { ROUTE_NAMES } from './routes.js';

export class ConfigError extends Error {}

// The browser gives up after this long (CLIENT_TIMEOUT_MS in frontend/src/api/client.js).
export const BROWSER_TIMEOUT_MS = 40000;
// The collector waits for one collection this much longer than COLLECTION_DEADLINE_MS
// (_TIMEOUT_MARGIN_SECONDS in backend/app/composition.py).
const COLLECTOR_MARGIN_MS = 5000;

function fail(variable, reason) {
  throw new ConfigError(`Invalid configuration: ${variable}: ${reason}`);
}

// Empty strings count as unset, so a blank line in an env file falls back to the default.
function read(env, variable, fallback) {
  const value = env[variable];
  return value === undefined || value === '' ? fallback : value;
}

function integer(env, variable, fallback, min, max) {
  const raw = read(env, variable, String(fallback));
  if (!/^-?\d+$/.test(raw)) fail(variable, 'must be a whole number');
  const value = Number(raw);
  if (value < min || value > max) fail(variable, `must be between ${min} and ${max}`);
  return value;
}

function text(env, variable, fallback) {
  const value = read(env, variable, fallback);
  if (value.trim() === '') fail(variable, 'must not be blank');
  return value;
}

function oneOf(env, variable, fallback, choices) {
  const value = read(env, variable, fallback);
  if (!choices.includes(value)) fail(variable, `must be one of: ${choices.join(', ')}`);
  return value;
}

// Each layer must outlast the one it waits for, so the user sees the real error:
// collector limit < INNER_TIMEOUT_MS < browser limit.
function innerTimeout(env) {
  const deadline = integer(env, 'COLLECTION_DEADLINE_MS', 25000, 5000, 60000);
  const timeout = integer(env, 'INNER_TIMEOUT_MS', 35000, 1000, 120000);
  const collectorLimit = deadline + COLLECTOR_MARGIN_MS;
  if (timeout <= collectorLimit) {
    fail('INNER_TIMEOUT_MS', `must be above ${collectorLimit} (COLLECTION_DEADLINE_MS + 5000)`);
  }
  if (timeout >= BROWSER_TIMEOUT_MS) {
    fail('INNER_TIMEOUT_MS', `must be below ${BROWSER_TIMEOUT_MS} (the browser's limit)`);
  }
  return timeout;
}

export function loadConfig(env) {
  return {
    port: integer(env, 'PORT', 3001, 0, 65535),
    host: text(env, 'HOST', '127.0.0.1'),
    innerHost: text(env, 'INNER_HOST', '127.0.0.1'),
    innerPort: integer(env, 'INNER_PORT', 3002, 0, 65535),
    apiRoutes: oneOf(env, 'API_ROUTES', 'rest', ROUTE_NAMES),
    innerTimeoutMs: innerTimeout(env),
  };
}
