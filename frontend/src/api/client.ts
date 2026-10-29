import type {
  CollectionResponse,
  ErrorBody,
  ErrorResponse,
  HealthResponse,
} from '@reddit-collector/contracts';

/** Error shown in the UI: a server error, or NETWORK when the backend cannot be reached. */
export type UiErrorBody = ErrorBody | { code: 'NETWORK'; message: string; retryable: true };

export class ApiError extends Error {
  constructor(
    readonly body: UiErrorBody,
    readonly lastGood?: CollectionResponse,
  ) {
    super(body.message);
    this.name = 'ApiError';
  }
}

export interface RequestOptions {
  signal?: AbortSignal;
  /** Above the backend's 25 s collection deadline, so the backend always answers first. */
  timeoutMs?: number;
  fetchImpl?: (url: string, init?: RequestInit) => Promise<Response>;
}

export const CLIENT_TIMEOUT_MS = 35_000;

export const DEFAULT_HEALTH: HealthResponse = {
  status: 'ok',
  db: 'ok',
  collectorMode: 'live',
  staleAfterSeconds: 600,
};

export const NETWORK_ERROR: UiErrorBody = {
  code: 'NETWORK',
  message: 'Cannot reach the local server. Is the backend running?',
  retryable: true,
};

export function collect(
  term: string,
  force: boolean,
  options: RequestOptions = {},
): Promise<CollectionResponse> {
  return request<CollectionResponse>(
    '/api/collections',
    {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ term, force }),
    },
    options,
  );
}

export function getPosts(term: string, options: RequestOptions = {}): Promise<CollectionResponse> {
  return request<CollectionResponse>(`/api/posts?term=${encodeURIComponent(term)}`, {}, options);
}

export async function getHealth(options: RequestOptions = {}): Promise<HealthResponse> {
  try {
    return await request<HealthResponse>('/api/health', {}, { timeoutMs: 5000, ...options });
  } catch {
    return DEFAULT_HEALTH;
  }
}

async function request<T>(url: string, init: RequestInit, options: RequestOptions): Promise<T> {
  const { signal, timeoutMs = CLIENT_TIMEOUT_MS, fetchImpl = fetch } = options;
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  const onCallerAbort = () => controller.abort();
  signal?.addEventListener('abort', onCallerAbort, { once: true });

  try {
    let response: Response;
    try {
      response = await fetchImpl(url, { ...init, signal: controller.signal });
    } catch {
      if (signal?.aborted) throw new DOMException('Request aborted', 'AbortError');
      throw new ApiError(NETWORK_ERROR);
    }
    const body: unknown = await response.json().catch(() => undefined);
    if (response.ok && body !== undefined) return body as T;
    if (isErrorResponse(body)) throw new ApiError(body.error, body.lastGood);
    throw new ApiError(NETWORK_ERROR);
  } finally {
    clearTimeout(timer);
    signal?.removeEventListener('abort', onCallerAbort);
  }
}

function isErrorResponse(body: unknown): body is ErrorResponse {
  const error = (body as { error?: Partial<ErrorBody> } | undefined)?.error;
  return (
    typeof error?.code === 'string' &&
    typeof error.message === 'string' &&
    typeof error.retryable === 'boolean'
  );
}
