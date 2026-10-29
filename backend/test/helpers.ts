import type { Post } from '@reddit-collector/contracts';
import type { Clock } from '../src/clock.js';

export function makePost(id: string, overrides: Partial<Post> = {}): Post {
  return {
    id,
    title: `Post ${id}`,
    author: 'someone',
    commentCount: 0,
    score: 1,
    createdAt: '2026-10-29T10:00:00.000Z',
    permalink: `https://www.reddit.com/r/ubisoft/comments/${id}/`,
    subreddit: 'ubisoft',
    previewText: null,
    flair: null,
    ...overrides,
  };
}

/** A clock that only moves when told to. */
export class FakeClock implements Clock {
  private current: Date;

  constructor(iso = '2026-10-29T12:00:00.000Z') {
    this.current = new Date(iso);
  }

  now(): Date {
    return new Date(this.current);
  }

  advanceSeconds(seconds: number): void {
    this.current = new Date(this.current.getTime() + seconds * 1000);
  }
}

export interface LoggedEntry {
  level: string;
  obj: object;
  msg: string;
}

export function makeLogger() {
  const entries: LoggedEntry[] = [];
  const log = (level: string) => (obj: object, msg: string) => entries.push({ level, obj, msg });
  return { entries, logger: { error: log('error'), warn: log('warn'), info: log('info') } };
}
