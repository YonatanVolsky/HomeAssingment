import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { z } from 'zod';
import type { Post } from '@reddit-collector/contracts';
import type { Clock } from '../clock.js';
import { AppError } from '../errors.js';
import type { Collector } from './types.js';

export const DEFAULT_SAMPLE_FILE = fileURLToPath(
  new URL('../../fixtures/sample-posts.json', import.meta.url),
);

const SamplePostSchema = z.object({
  key: z.string().regex(/^[a-z0-9_]+$/),
  title: z.string().min(1),
  author: z.string().nullable(),
  commentCount: z.number().int().min(0),
  score: z.number().int(),
  minutesAgo: z.number().min(0),
  previewText: z.string().nullable(),
  flair: z.string().nullable(),
});
export type SamplePost = z.infer<typeof SamplePostSchema>;

/** Subreddit names that simulate an outcome, so every UI state can be shown offline. */
const SIMULATED_FAILURES: Record<string, () => AppError> = {
  notfound: () => new AppError('NOT_FOUND_SUBREDDIT'),
  ratelimited: () => new AppError('RATE_LIMITED', undefined, { retryAfterSeconds: 30 }),
  broken: () => new AppError('UPSTREAM_ERROR'),
  timeout: () => new AppError('UPSTREAM_TIMEOUT'),
};

/** Offline sample data (COLLECTOR_MODE=fixture). Never calls Reddit. */
export class FixtureCollector implements Collector {
  constructor(
    private readonly samples: SamplePost[],
    private readonly clock: Clock,
  ) {}

  static fromFile(path: string, clock: Clock): FixtureCollector {
    const samples = z.array(SamplePostSchema).parse(JSON.parse(readFileSync(path, 'utf8')));
    return new FixtureCollector(samples, clock);
  }

  async collect(subreddit: string, limit: number): Promise<Post[]> {
    const failure = SIMULATED_FAILURES[subreddit];
    if (failure) throw failure();
    if (subreddit === 'empty') return [];
    const now = this.clock.now().getTime();
    return this.samples.slice(0, limit).map((sample) => {
      const slug = `fx_${subreddit}_${sample.key}`;
      return {
        id: `t3_${slug}`,
        title: sample.title,
        author: sample.author,
        commentCount: sample.commentCount,
        score: sample.score,
        createdAt: new Date(now - sample.minutesAgo * 60_000).toISOString(),
        permalink: `https://www.reddit.com/r/${subreddit}/comments/${slug}/`,
        subreddit,
        previewText: sample.previewText,
        flair: sample.flair,
      };
    });
  }
}
