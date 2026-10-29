import { setTimeout as delay } from 'node:timers/promises';
import type { Post } from '@reddit-collector/contracts';
import type { AppError } from '../errors.js';
import { classifyNetworkError } from './classify.js';
import { Deadline } from './deadline.js';
import type { Collector } from './types.js';

/** Sends the app's listing request and parses it. Reddit-specific; built from the capture. */
export interface ListingSource {
  fetchNewPosts(
    subreddit: string,
    limit: number,
    token: string,
    signal: AbortSignal,
  ): Promise<Post[]>;
}

export interface TokenSource {
  get(signal: AbortSignal): Promise<string>;
  /** Drops `rejectedToken` if it is still the cached one. */
  invalidate(rejectedToken: string): void;
}

export interface RedditCollectorDeps {
  tokens: TokenSource;
  source: ListingSource;
  deadlineMs: number;
  maxRetries?: number;
  baseDelayMs?: number;
  random?: () => number;
  sleep?: (ms: number, signal: AbortSignal) => Promise<void>;
}

/**
 * The reliability policy around Reddit: one deadline per collection, auto-retry with
 * backoff for transient failures (as the error table says), and one token refresh on
 * an auth failure. Knows nothing about Reddit's request or response format.
 */
export class RedditCollector implements Collector {
  private readonly maxRetries: number;
  private readonly baseDelayMs: number;
  private readonly random: () => number;
  private readonly sleep: (ms: number, signal: AbortSignal) => Promise<void>;

  constructor(private readonly deps: RedditCollectorDeps) {
    this.maxRetries = deps.maxRetries ?? 2;
    this.baseDelayMs = deps.baseDelayMs ?? 250;
    this.random = deps.random ?? Math.random;
    this.sleep = deps.sleep ?? ((ms, signal) => delay(ms, undefined, { signal }));
  }

  async collect(subreddit: string, limit: number): Promise<Post[]> {
    const deadline = new Deadline(this.deps.deadlineMs);
    try {
      return await this.withRetry(
        deadline,
        this.attemptWithAuthRefresh(subreddit, limit, deadline),
      );
    } finally {
      deadline.dispose();
    }
  }

  /** One attempt; on the first auth failure of this collection, refresh the token and resend. */
  private attemptWithAuthRefresh(subreddit: string, limit: number, deadline: Deadline) {
    let refreshed = false;
    let sentToken: string | undefined;
    const send = async (): Promise<Post[]> => {
      sentToken = undefined;
      const token = await this.deps.tokens.get(deadline.signal);
      sentToken = token;
      return this.deps.source.fetchNewPosts(subreddit, limit, token, deadline.signal);
    };
    return async (): Promise<Post[]> => {
      try {
        return await send();
      } catch (error) {
        if (refreshed || classifyNetworkError(error).code !== 'UPSTREAM_AUTH') throw error;
        refreshed = true;
        if (sentToken !== undefined) this.deps.tokens.invalidate(sentToken);
        return send();
      }
    };
  }

  private async withRetry(deadline: Deadline, attempt: () => Promise<Post[]>): Promise<Post[]> {
    for (let retry = 0; ; retry += 1) {
      let error: AppError;
      try {
        return await attempt();
      } catch (raw) {
        if (deadline.expired) throw Deadline.error(raw);
        error = classifyNetworkError(raw);
      }
      if (!error.autoRetry || retry >= this.maxRetries) throw error;
      const backoff = this.baseDelayMs * 2 ** retry + this.random() * this.baseDelayMs;
      if (backoff >= deadline.remainingMs()) throw error;
      try {
        await this.sleep(backoff, deadline.signal);
      } catch (cause) {
        throw Deadline.error(cause);
      }
    }
  }
}
