import { AppError } from '../errors.js';

export type Headers = Record<string, string | string[] | undefined>;

const DEFAULT_RETRY_AFTER_SECONDS = 30;
const TIMEOUT_CODES = new Set([
  'UND_ERR_CONNECT_TIMEOUT',
  'UND_ERR_HEADERS_TIMEOUT',
  'UND_ERR_BODY_TIMEOUT',
  'ETIMEDOUT',
]);

/** Maps an HTTP status from Reddit to an AppError, or null for success. */
export function classifyStatus(status: number, headers: Headers): AppError | null {
  if (status >= 200 && status < 300) return null;
  const cause = new Error(`Reddit responded with HTTP ${status}`);
  if (status === 401 || status === 403) return new AppError('UPSTREAM_AUTH', undefined, { cause });
  if (status === 404) return new AppError('NOT_FOUND_SUBREDDIT', undefined, { cause });
  if (status === 429) {
    return new AppError('RATE_LIMITED', undefined, {
      cause,
      retryAfterSeconds: retryAfterSeconds(headers),
    });
  }
  if (status >= 500) return new AppError('UPSTREAM_ERROR', undefined, { cause });
  return new AppError('UPSTREAM_ERROR', undefined, { cause, autoRetry: false });
}

/** Maps a thrown network or timeout error to an AppError. AppErrors pass through. */
export function classifyNetworkError(error: unknown): AppError {
  if (error instanceof AppError) return error;
  const code = (error as { code?: unknown } | null)?.code;
  const isTimeout =
    (typeof code === 'string' && TIMEOUT_CODES.has(code)) ||
    (error instanceof Error && error.name === 'TimeoutError');
  return new AppError(isTimeout ? 'UPSTREAM_TIMEOUT' : 'UPSTREAM_ERROR', undefined, {
    cause: error,
  });
}

function retryAfterSeconds(headers: Headers): number {
  for (const name of ['retry-after', 'x-ratelimit-reset']) {
    const raw = headers[name];
    const value = Number(Array.isArray(raw) ? raw[0] : raw);
    if (raw !== undefined && Number.isFinite(value) && value > 0) return Math.ceil(value);
  }
  return DEFAULT_RETRY_AFTER_SECONDS;
}
