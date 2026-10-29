/** Error shown in the UI: a server error, or NETWORK when the backend cannot be reached. */
export class ApiError extends Error {
  body;
  lastGood;
  constructor(body, lastGood) {
    super(body.message);
    this.body = body;
    this.lastGood = lastGood;
    this.name = 'ApiError';
  }
}

/** Above the backend's 25 s collection deadline, so the backend always answers first. */
export const CLIENT_TIMEOUT_MS = 35_000;

export const DEFAULT_HEALTH = {
  status: 'ok',
  db: 'ok',
  collectorMode: 'live',
  staleAfterSeconds: 600,
};

export const NETWORK_ERROR = {
  code: 'NETWORK',
  message: 'Cannot reach the local server. Is the backend running?',
  retryable: true,
};

export function collect(term, force, options = {}) {
  return request(
    '/api/collections',
    {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ term, force }),
    },
    options,
  );
}

export function getPosts(term, options = {}) {
  return request(`/api/posts?term=${encodeURIComponent(term)}`, {}, options);
}

export async function getHealth(options = {}) {
  try {
    return await request('/api/health', {}, { timeoutMs: 5000, ...options });
  } catch {
    return DEFAULT_HEALTH;
  }
}

async function request(url, init, options) {
  const { signal, timeoutMs = CLIENT_TIMEOUT_MS, fetchImpl = fetch } = options;
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  const onCallerAbort = () => controller.abort();
  signal?.addEventListener('abort', onCallerAbort, { once: true });
  try {
    let response;
    try {
      response = await fetchImpl(url, { ...init, signal: controller.signal });
    } catch {
      if (signal?.aborted) throw new DOMException('Request aborted', 'AbortError');
      throw new ApiError(NETWORK_ERROR);
    }
    const body = await response.json().catch(() => undefined);
    if (response.ok && body !== undefined) return body;
    if (isErrorResponse(body)) throw new ApiError(body.error, body.lastGood);
    throw new ApiError(NETWORK_ERROR);
  } finally {
    clearTimeout(timer);
    signal?.removeEventListener('abort', onCallerAbort);
  }
}

function isErrorResponse(body) {
  const error = body?.error;
  return (
    typeof error?.code === 'string' &&
    typeof error.message === 'string' &&
    typeof error.retryable === 'boolean'
  );
}
