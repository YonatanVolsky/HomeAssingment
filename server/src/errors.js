// HTTP status for every error code the browser can see, and the web service's own errors.

const STATUS = {
  INVALID_TERM: 400,
  INVALID_REQUEST: 400,
  NOT_FOUND_SUBREDDIT: 404,
  NOT_FOUND: 404,
  RATE_LIMITED: 429,
  DB_ERROR: 500,
  INTERNAL: 500,
  UPSTREAM_AUTH: 502,
  UPSTREAM_ERROR: 502,
  CONTRACT_ERROR: 502,
  INNER_UNAVAILABLE: 503,
  UPSTREAM_TIMEOUT: 504,
};

// Errors raised here rather than by the inner server; same shape as the inner server's.
const OWN_ERRORS = {
  INNER_UNAVAILABLE: { message: 'The collector service is not running.', retryable: true },
  UPSTREAM_TIMEOUT: { message: 'Reddit took too long to respond.', retryable: true },
  INTERNAL: { message: 'Something went wrong.', retryable: true },
  NOT_FOUND: { message: 'Not found.', retryable: false },
  INVALID_REQUEST: { message: 'The request is not valid.', retryable: false },
};

export function statusFor(code) {
  return STATUS[code] ?? 500;
}

export function errorBody(code) {
  const known = OWN_ERRORS[code] ?? OWN_ERRORS.INTERNAL;
  return { code: OWN_ERRORS[code] ? code : 'INTERNAL', ...known };
}

/** A failure talking to the inner server, with one of the codes above. */
export class InnerError extends Error {
  constructor(code, options) {
    super(code, options);
    this.name = 'InnerError';
    this.code = code;
  }
}
