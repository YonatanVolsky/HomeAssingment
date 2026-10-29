import type { Clock } from '../clock.js';
import { AppError } from '../errors.js';
import type { Logger } from '../logger.js';

export interface FetchedToken {
  accessToken: string;
  expiresInSeconds: number;
}

/** Performs the app's anonymous token request. Reddit-specific; see docs/reddit-mobile-request.md. */
export type TokenFetcher = (signal: AbortSignal) => Promise<FetchedToken>;

const REFRESH_MARGIN_MS = 60_000;
const PASS_THROUGH = new Set(['UPSTREAM_TIMEOUT', 'RATE_LIMITED']);

/**
 * Caches the anonymous token until shortly before it expires. Concurrent callers share
 * one refresh. Failures are not cached, and the token value is never logged.
 */
export class TokenProvider {
  private cached: { token: string; expiresAt: number } | null = null;
  private inFlight: Promise<string> | null = null;

  constructor(
    private readonly fetchToken: TokenFetcher,
    private readonly clock: Clock,
    private readonly logger: Logger,
  ) {}

  async get(signal: AbortSignal): Promise<string> {
    const now = this.clock.now().getTime();
    if (this.cached && now < this.cached.expiresAt - REFRESH_MARGIN_MS) {
      return this.cached.token;
    }
    this.inFlight ??= this.refresh(signal).finally(() => {
      this.inFlight = null;
    });
    return this.inFlight;
  }

  invalidate(): void {
    this.cached = null;
  }

  private async refresh(signal: AbortSignal): Promise<string> {
    let fetched: FetchedToken;
    try {
      fetched = await this.fetchToken(signal);
    } catch (cause) {
      if (cause instanceof AppError && PASS_THROUGH.has(cause.code)) throw cause;
      throw new AppError('UPSTREAM_AUTH', undefined, { cause });
    }
    this.cached = {
      token: fetched.accessToken,
      expiresAt: this.clock.now().getTime() + fetched.expiresInSeconds * 1000,
    };
    this.logger.info(
      { validForSeconds: fetched.expiresInSeconds },
      `token refreshed, valid for ${fetched.expiresInSeconds} s`,
    );
    return fetched.accessToken;
  }
}
