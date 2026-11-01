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

/** Above the web service's 35 s wait for the collector, so the server always answers first. */
export const CLIENT_TIMEOUT_MS = 40_000;

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

/**
 * The feed for a term. `freshness`: 'auto' (stored if recent, else collected live),
 * 'live' (always collect) or 'stored' (never call Reddit).
 */
export function getFeed(term, freshness, options = {}) {
  const query = `term=${encodeURIComponent(term)}&freshness=${encodeURIComponent(freshness)}`;
  return request(`/api/posts?${query}`, {}, options);
}

/**
 * The server's health, or DEFAULT_HEALTH if it cannot be read. `attempts` > 1 retries
 * every `intervalMs`, for a page opened while the collector is still starting.
 */
export async function getHealth({ attempts = 1, intervalMs = 500, ...options } = {}) {
  for (let attempt = 1; attempt <= attempts; attempt++) {
    try {
      return await request('/api/health', {}, { timeoutMs: 5000, ...options });
    } catch {
      if (options.signal?.aborted || attempt === attempts) break;
      await new Promise((resolve) => setTimeout(resolve, intervalMs));
    }
  }
  return DEFAULT_HEALTH;
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
