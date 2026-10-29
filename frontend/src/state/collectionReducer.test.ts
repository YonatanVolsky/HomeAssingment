import type { CollectionResponse } from '@reddit-collector/contracts';
import { describe, expect, it } from 'vitest';
import { collectionReducer, type View } from './collectionReducer';

const withPosts: CollectionResponse = {
  collection: {
    id: 1,
    term: 'ubisoft',
    source: 'live',
    collectedAt: '2026-10-29T12:00:00.000Z',
    postCount: 1,
  },
  posts: [
    {
      id: 't3_a',
      title: 'A',
      author: 'x',
      commentCount: 0,
      score: 1,
      createdAt: '2026-10-29T11:00:00.000Z',
      permalink: 'https://www.reddit.com/r/ubisoft/comments/a/',
      subreddit: 'ubisoft',
      previewText: null,
      flair: null,
    },
  ],
};
const noPosts: CollectionResponse = {
  collection: {
    id: 2,
    term: 'quiet',
    source: 'live',
    collectedAt: '2026-10-29T12:00:00.000Z',
    postCount: 0,
  },
  posts: [],
};
const timeout = { code: 'UPSTREAM_TIMEOUT', message: 'slow', retryable: true } as const;
const notFound = { code: 'NOT_FOUND_SUBREDDIT', message: 'nope', retryable: false } as const;

const idle: View = { kind: 'idle' };
const loading: View = { kind: 'loading', term: 'ubisoft', force: false };

describe('collectionReducer', () => {
  it('moves from idle to loading on submit', () => {
    expect(collectionReducer(idle, { type: 'submit', term: 'ubisoft', force: true })).toEqual({
      kind: 'loading',
      term: 'ubisoft',
      force: true,
    });
  });

  it('keeps the current feed as previous while loading', () => {
    const success: View = { kind: 'success', data: withPosts };
    expect(collectionReducer(success, { type: 'submit', term: 'gaming', force: false })).toEqual({
      kind: 'loading',
      term: 'gaming',
      force: false,
      previous: withPosts,
    });
  });

  it('keeps the last good feed of an error as previous while loading', () => {
    const error: View = { kind: 'error', term: 'ubisoft', error: timeout, lastGood: withPosts };
    expect(
      collectionReducer(error, { type: 'submit', term: 'ubisoft', force: false }),
    ).toMatchObject({ kind: 'loading', previous: withPosts });
  });

  it('ignores a submit while loading', () => {
    expect(collectionReducer(loading, { type: 'submit', term: 'other', force: false })).toBe(
      loading,
    );
  });

  it('shows success when the response has posts', () => {
    expect(collectionReducer(loading, { type: 'resolved', data: withPosts })).toEqual({
      kind: 'success',
      data: withPosts,
    });
  });

  it('shows empty when the response has no posts', () => {
    expect(collectionReducer(loading, { type: 'resolved', data: noPosts })).toEqual({
      kind: 'empty',
      data: noPosts,
    });
  });

  it('shows the error with the last good feed from the server', () => {
    expect(
      collectionReducer(loading, { type: 'failed', error: timeout, lastGood: withPosts }),
    ).toEqual({ kind: 'error', term: 'ubisoft', error: timeout, lastGood: withPosts });
  });

  it('falls back to the previous feed when the server sent no last good feed', () => {
    const loadingWithPrevious: View = { ...loading, previous: withPosts };
    expect(
      collectionReducer(loadingWithPrevious, { type: 'failed', error: timeout }),
    ).toMatchObject({
      lastGood: withPosts,
    });
  });

  it('retries a retryable error with the same term and without force', () => {
    const error: View = { kind: 'error', term: 'ubisoft', error: timeout, lastGood: withPosts };
    expect(collectionReducer(error, { type: 'retry' })).toEqual({
      kind: 'loading',
      term: 'ubisoft',
      force: false,
      previous: withPosts,
    });
  });

  it('does not retry an error that is not retryable', () => {
    const error: View = { kind: 'error', term: 'x', error: notFound };
    expect(collectionReducer(error, { type: 'retry' })).toBe(error);
  });

  it('ignores a late response when not loading', () => {
    const success: View = { kind: 'success', data: withPosts };
    expect(collectionReducer(success, { type: 'resolved', data: noPosts })).toBe(success);
    expect(collectionReducer(success, { type: 'failed', error: timeout })).toBe(success);
  });

  it('restores a stored feed only from idle', () => {
    expect(collectionReducer(idle, { type: 'restored', data: withPosts })).toEqual({
      kind: 'success',
      data: withPosts,
    });
    expect(collectionReducer(loading, { type: 'restored', data: withPosts })).toBe(loading);
  });

  it('ignores a restore of a term that was never collected', () => {
    expect(
      collectionReducer(idle, { type: 'restored', data: { collection: null, posts: [] } }),
    ).toBe(idle);
  });
});
