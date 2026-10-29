import { describe, expect, it } from 'vitest';
import { rowToPost, rowToStoredCollection } from '../../../src/db/rows.js';

describe('rowToPost', () => {
  it('maps snake_case columns to the Post contract', () => {
    const post = rowToPost({
      reddit_id: 't3_abc',
      title: 'Hello',
      author: null,
      comment_count: 3,
      score: -2,
      created_at: '2026-10-29T10:00:00.000Z',
      permalink: 'https://www.reddit.com/r/ubisoft/comments/abc/hello/',
      subreddit: 'ubisoft',
      preview_text: null,
      flair: 'Question',
    });

    expect(post).toEqual({
      id: 't3_abc',
      title: 'Hello',
      author: null,
      commentCount: 3,
      score: -2,
      createdAt: '2026-10-29T10:00:00.000Z',
      permalink: 'https://www.reddit.com/r/ubisoft/comments/abc/hello/',
      subreddit: 'ubisoft',
      previewText: null,
      flair: 'Question',
    });
  });
});

describe('rowToStoredCollection', () => {
  it('uses finished_at as the collection time', () => {
    expect(
      rowToStoredCollection({
        id: 7,
        term: 'ubisoft',
        post_count: 25,
        finished_at: '2026-10-29T10:00:05.000Z',
      }),
    ).toEqual({ id: 7, term: 'ubisoft', postCount: 25, collectedAt: '2026-10-29T10:00:05.000Z' });
  });
});
