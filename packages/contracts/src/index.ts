/**
 * Shared API types between backend and frontend. Type-only: import with
 * `import type` so nothing from this package exists at runtime.
 * All timestamps are ISO 8601 UTC strings; all counts are non-negative integers
 * except `score`, which may be negative.
 */

export interface Post {
  /** Reddit fullname, e.g. `t3_abc123`. Stable identity. */
  id: string;
  title: string;
  /** `null` for deleted or anonymous authors. */
  author: string | null;
  commentCount: number;
  score: number;
  createdAt: string;
  /** Absolute `https://www.reddit.com/...` URL. */
  permalink: string;
  /** Without the `r/` prefix. */
  subreddit: string | null;
  /** Plain text, at most 300 characters. */
  previewText: string | null;
  flair: string | null;
}

export type CollectionSource = 'live' | 'cache';

/** Always describes a successful run. */
export interface CollectionSummary {
  id: number;
  term: string;
  /** `cache` means served from the database without calling Reddit. */
  source: CollectionSource;
  collectedAt: string;
  postCount: number;
}

export interface CollectionResponse {
  /** `null` only from `GET /api/posts` when the term was never collected. */
  collection: CollectionSummary | null;
  /** Newest first. */
  posts: Post[];
}

export type ErrorCode =
  | 'INVALID_TERM'
  | 'RATE_LIMITED'
  | 'UPSTREAM_AUTH'
  | 'UPSTREAM_ERROR'
  | 'UPSTREAM_TIMEOUT'
  | 'NOT_FOUND_SUBREDDIT'
  | 'CONTRACT_ERROR'
  | 'DB_ERROR'
  | 'INTERNAL';

export interface ErrorBody {
  code: ErrorCode;
  /** Safe for display; contains no internals. */
  message: string;
  /** Whether the UI should offer "Try again". */
  retryable: boolean;
  /** Only for `RATE_LIMITED`. */
  retryAfterSeconds?: number;
}

export interface ErrorResponse {
  error: ErrorBody;
  /** Previous successful feed for the term, if any. */
  lastGood?: CollectionResponse;
}

export interface CollectRequest {
  term: string;
  /** Bypasses the result cache. */
  force?: boolean;
}

export type CollectorMode = 'live' | 'fixture';

export interface HealthResponse {
  status: 'ok' | 'error';
  db: 'ok' | 'error';
  collectorMode: CollectorMode;
  staleAfterSeconds: number;
}
