import { z } from 'zod';
import type { CollectorMode } from '@reddit-collector/contracts';

export interface Config {
  port: number;
  host: string;
  collectorMode: CollectorMode;
  dbPath: string;
  maxPosts: number;
  collectionTtlSeconds: number;
  staleAfterSeconds: number;
  requestTimeoutMs: number;
  collectionDeadlineMs: number;
  logLevel: 'fatal' | 'error' | 'warn' | 'info' | 'debug' | 'trace' | 'silent';
}

const int = (min: number, max: number, fallback: number) =>
  z.coerce.number().int().min(min).max(max).default(fallback);

const EnvSchema = z
  .object({
    PORT: int(1, 65535, 3001),
    HOST: z.string().min(1).default('127.0.0.1'),
    COLLECTOR_MODE: z.enum(['live', 'fixture']).default('live'),
    DB_PATH: z.string().min(1).optional(),
    MAX_POSTS: int(1, 100, 25),
    COLLECTION_TTL_SECONDS: int(0, 3600, 60),
    STALE_AFTER_SECONDS: int(1, 7 * 24 * 3600, 600),
    REQUEST_TIMEOUT_MS: int(1000, 20000, 8000),
    COLLECTION_DEADLINE_MS: int(5000, 60000, 25000),
    LOG_LEVEL: z
      .enum(['fatal', 'error', 'warn', 'info', 'debug', 'trace', 'silent'])
      .default('info'),
  })
  .refine((env) => env.REQUEST_TIMEOUT_MS < env.COLLECTION_DEADLINE_MS, {
    path: ['REQUEST_TIMEOUT_MS'],
    message: 'must be below COLLECTION_DEADLINE_MS',
  });

export class ConfigError extends Error {}

/**
 * Parses the environment once. Nothing else in the backend reads `process.env`.
 * Empty strings count as unset, so a blank line in `.env` falls back to the default.
 */
export function loadConfig(env: Record<string, string | undefined>): Readonly<Config> {
  const present = Object.fromEntries(Object.entries(env).filter(([, value]) => value !== ''));
  const result = EnvSchema.safeParse(present);
  if (!result.success) {
    const problems = result.error.issues
      .map((issue) => `${issue.path.join('.')}: ${issue.message}`)
      .join('; ');
    throw new ConfigError(`Invalid configuration: ${problems}`);
  }
  const e = result.data;
  return Object.freeze({
    port: e.PORT,
    host: e.HOST,
    collectorMode: e.COLLECTOR_MODE,
    dbPath:
      e.DB_PATH ?? (e.COLLECTOR_MODE === 'fixture' ? './data/fixture.db' : './data/collector.db'),
    maxPosts: e.MAX_POSTS,
    collectionTtlSeconds: e.COLLECTION_TTL_SECONDS,
    staleAfterSeconds: e.STALE_AFTER_SECONDS,
    requestTimeoutMs: e.REQUEST_TIMEOUT_MS,
    collectionDeadlineMs: e.COLLECTION_DEADLINE_MS,
    logLevel: e.LOG_LEVEL,
  });
}
