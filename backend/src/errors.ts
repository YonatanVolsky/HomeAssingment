import type { ErrorBody, ErrorCode } from '@reddit-collector/contracts';

export interface ErrorPolicy {
  httpStatus: number;
  /** Whether the collector re-sends the same request itself before giving up. */
  autoRetry: boolean;
  /** Whether the UI offers "Try again" without the user changing the input. */
  retryable: boolean;
  defaultMessage: string;
}

/** The single source of truth for how each error behaves. See plan/00. */
export const ERROR_TABLE: Readonly<Record<ErrorCode, ErrorPolicy>> = Object.freeze({
  INVALID_TERM: {
    httpStatus: 400,
    autoRetry: false,
    retryable: false,
    defaultMessage: 'Enter a subreddit name like r/ubisoft.',
  },
  RATE_LIMITED: {
    httpStatus: 429,
    autoRetry: false,
    retryable: true,
    defaultMessage: 'Reddit is limiting requests. Try again shortly.',
  },
  UPSTREAM_AUTH: {
    httpStatus: 502,
    autoRetry: false,
    retryable: true,
    defaultMessage: 'Could not authenticate with Reddit.',
  },
  UPSTREAM_ERROR: {
    httpStatus: 502,
    autoRetry: true,
    retryable: true,
    defaultMessage: 'Reddit is unavailable right now.',
  },
  UPSTREAM_TIMEOUT: {
    httpStatus: 504,
    autoRetry: true,
    retryable: true,
    defaultMessage: 'Reddit took too long to respond.',
  },
  NOT_FOUND_SUBREDDIT: {
    httpStatus: 404,
    autoRetry: false,
    retryable: false,
    defaultMessage: 'That subreddit was not found or is not public.',
  },
  CONTRACT_ERROR: {
    httpStatus: 502,
    autoRetry: false,
    retryable: true,
    defaultMessage: 'Reddit returned an unexpected response.',
  },
  DB_ERROR: {
    httpStatus: 500,
    autoRetry: false,
    retryable: true,
    defaultMessage: 'Could not save results locally.',
  },
  INTERNAL: {
    httpStatus: 500,
    autoRetry: false,
    retryable: true,
    defaultMessage: 'Something went wrong.',
  },
});

export interface AppErrorOptions {
  cause?: unknown;
  retryAfterSeconds?: number;
  /** Only `false` is meaningful: stops the collector re-sending a request the table would retry. */
  autoRetry?: false;
}

/**
 * An error whose message is safe to show to users. `cause` is for logs only
 * and is never serialized into a response.
 */
export class AppError extends Error {
  readonly code: ErrorCode;
  readonly retryAfterSeconds: number | undefined;
  private readonly autoRetryOverride: false | undefined;

  constructor(code: ErrorCode, message?: string, options: AppErrorOptions = {}) {
    super(message ?? defaultMessage(code, options.retryAfterSeconds), { cause: options.cause });
    this.name = 'AppError';
    this.code = code;
    this.retryAfterSeconds = options.retryAfterSeconds;
    this.autoRetryOverride = options.autoRetry;
  }

  get httpStatus(): number {
    return ERROR_TABLE[this.code].httpStatus;
  }

  get retryable(): boolean {
    return ERROR_TABLE[this.code].retryable;
  }

  get autoRetry(): boolean {
    return this.autoRetryOverride ?? ERROR_TABLE[this.code].autoRetry;
  }
}

function defaultMessage(code: ErrorCode, retryAfterSeconds?: number): string {
  if (code === 'RATE_LIMITED' && retryAfterSeconds !== undefined) {
    return `Reddit is limiting requests. Try again in ${retryAfterSeconds} seconds.`;
  }
  return ERROR_TABLE[code].defaultMessage;
}

export function isAppError(value: unknown): value is AppError {
  return value instanceof AppError;
}

export function toErrorBody(error: AppError): ErrorBody {
  return {
    code: error.code,
    message: error.message,
    retryable: error.retryable,
    ...(error.retryAfterSeconds !== undefined && { retryAfterSeconds: error.retryAfterSeconds }),
  };
}
