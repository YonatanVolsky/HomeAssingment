import type { Post } from '@reddit-collector/contracts';

/** Turns a normalized subreddit name into posts, or throws an AppError. */
export interface Collector {
  collect(subreddit: string, limit: number): Promise<Post[]>;
}
