import type { Post } from '@reddit-collector/contracts';

export function makePost(id: string, overrides: Partial<Post> = {}): Post {
  return {
    id,
    title: `Post ${id}`,
    author: 'someone',
    commentCount: 0,
    score: 1,
    createdAt: '2026-10-29T11:11:00.000Z',
    permalink: `https://www.reddit.com/r/ubisoft/comments/${id}/`,
    subreddit: 'ubisoft',
    previewText: null,
    flair: null,
    ...overrides,
  };
}

export const NOW = new Date('2026-10-29T12:00:00.000Z');
