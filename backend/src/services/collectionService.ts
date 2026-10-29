import type { CollectionResponse, CollectionSource } from '@reddit-collector/contracts';
import type { Clock } from '../clock.js';
import { normalizeTerm } from '../collector/normalizeTerm.js';
import type { Collector } from '../collector/types.js';
import type { Config } from '../config.js';
import type { CollectionRepository } from '../db/repository.js';
import type { StoredCollection } from '../db/rows.js';
import { AppError } from '../errors.js';
import type { Logger } from '../logger.js';

export interface CollectionServiceDeps {
  repository: CollectionRepository;
  collector: Collector;
  clock: Clock;
  config: Pick<Config, 'maxPosts' | 'collectionTtlSeconds'>;
  logger: Logger;
}

/**
 * Orchestrates one collection: validate the term, serve a fresh stored result if there is
 * one, otherwise collect live (sharing a run already in progress for the same term), and
 * store the outcome. What the user sees is always read back from the database.
 */
export class CollectionService {
  private readonly inFlight = new Map<string, Promise<CollectionResponse>>();

  constructor(private readonly deps: CollectionServiceDeps) {}

  collect(term: string, force: boolean): Promise<CollectionResponse> {
    let subreddit: string;
    let fresh: StoredCollection | null = null;
    try {
      subreddit = normalizeTerm(term);
      if (!force) {
        fresh = this.deps.repository.getFreshSuccess(
          subreddit,
          this.deps.config.collectionTtlSeconds,
        );
      }
    } catch (error) {
      return Promise.reject(error);
    }
    if (fresh) return Promise.resolve(this.toResponse(fresh, 'cache'));

    const running = this.inFlight.get(subreddit);
    if (running) return running;

    const run = this.collectLive(subreddit).finally(() => this.inFlight.delete(subreddit));
    this.inFlight.set(subreddit, run);
    return run;
  }

  /** The previous successful feed for a term, or undefined. Best effort: never throws. */
  lastGood(term: string): CollectionResponse | undefined {
    try {
      const latest = this.deps.repository.getLatestSuccess(normalizeTerm(term));
      return latest ? this.toResponse(latest, 'cache') : undefined;
    } catch (error) {
      if (!(error instanceof AppError && error.code === 'INVALID_TERM')) {
        this.deps.logger.warn({ err: error }, 'could not load the last good feed');
      }
      return undefined;
    }
  }

  /** Reads the stored feed only; never calls Reddit. */
  getPosts(term: string): CollectionResponse {
    const latest = this.deps.repository.getLatestSuccess(normalizeTerm(term));
    return latest ? this.toResponse(latest, 'cache') : { collection: null, posts: [] };
  }

  private async collectLive(subreddit: string): Promise<CollectionResponse> {
    const startedAt = this.deps.clock.now();
    try {
      const posts = await this.deps.collector.collect(subreddit, this.deps.config.maxPosts);
      const stored = this.deps.repository.recordSuccess(subreddit, posts, startedAt);
      return this.toResponse(stored, 'live');
    } catch (raw) {
      const error =
        raw instanceof AppError ? raw : new AppError('INTERNAL', undefined, { cause: raw });
      this.deps.repository.recordFailure(subreddit, error.code, startedAt);
      throw error;
    }
  }

  private toResponse(stored: StoredCollection, source: CollectionSource): CollectionResponse {
    return {
      collection: { ...stored, source },
      posts: this.deps.repository.getFeed(stored.id),
    };
  }
}
