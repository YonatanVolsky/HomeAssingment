// Environment configuration for the web service, read once at startup.
import { ROUTE_NAMES } from './routes.js';

export class ConfigError extends Error {}

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

export function loadConfig(env) {
  return {
    port: integer(env, 'PORT', 3001, 0, 65535),
    host: text(env, 'HOST', '127.0.0.1'),
    innerHost: text(env, 'INNER_HOST', '127.0.0.1'),
    innerPort: integer(env, 'INNER_PORT', 3002, 0, 65535),
    apiRoutes: oneOf(env, 'API_ROUTES', 'rest', ROUTE_NAMES),
    // Above the inner server's own 30 s limit (25 s collection deadline + 5 s margin).
    innerTimeoutMs: integer(env, 'INNER_TIMEOUT_MS', 35000, 1000, 120000),
  };
}
