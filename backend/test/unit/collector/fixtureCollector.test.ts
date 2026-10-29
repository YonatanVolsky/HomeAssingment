import { describe, expect, it } from 'vitest';
import {
  DEFAULT_SAMPLE_FILE,
  FixtureCollector,
  type SamplePost,
} from '../../../src/collector/fixtureCollector.js';
import { FakeClock } from '../../helpers.js';

const samples: SamplePost[] = [
  {
    key: 'one',
    title: 'First',
    author: 'alice',
    commentCount: 3,
    score: 10,
    minutesAgo: 5,
    previewText: 'Hello',
    flair: 'Question',
  },
  {
    key: 'two',
    title: 'Second',
    author: null,
    commentCount: 0,
    score: -1,
    minutesAgo: 90,
    previewText: null,
    flair: null,
  },
];

const collector = () => new FixtureCollector(samples, new FakeClock('2026-10-29T12:00:00.000Z'));

describe('FixtureCollector', () => {
  it('returns sample posts for the requested subreddit, timed relative to now', async () => {
    const posts = await collector().collect('ubisoft', 25);

    expect(posts[0]).toEqual({
      id: 't3_fx_ubisoft_one',
      title: 'First',
      author: 'alice',
      commentCount: 3,
      score: 10,
      createdAt: '2026-10-29T11:55:00.000Z',
      permalink: 'https://www.reddit.com/r/ubisoft/comments/fx_ubisoft_one/',
      subreddit: 'ubisoft',
      previewText: 'Hello',
      flair: 'Question',
    });
    expect(posts[1]?.author).toBeNull();
  });

  it('respects the limit', async () => {
    expect(await collector().collect('ubisoft', 1)).toHaveLength(1);
  });

  it('returns no posts for the subreddit "empty"', async () => {
    expect(await collector().collect('empty', 25)).toEqual([]);
  });

  it.each([
    ['notfound', 'NOT_FOUND_SUBREDDIT'],
    ['ratelimited', 'RATE_LIMITED'],
    ['broken', 'UPSTREAM_ERROR'],
    ['timeout', 'UPSTREAM_TIMEOUT'],
  ])('simulates a failure for "%s"', async (term, code) => {
    await expect(collector().collect(term, 25)).rejects.toMatchObject({ code });
  });

  it('loads the bundled sample file', async () => {
    const fromFile = FixtureCollector.fromFile(DEFAULT_SAMPLE_FILE, new FakeClock());
    const posts = await fromFile.collect('ubisoft', 25);

    expect(posts.length).toBeGreaterThanOrEqual(5);
    expect(
      posts.every((post) => post.permalink.startsWith('https://www.reddit.com/r/ubisoft/')),
    ).toBe(true);
  });
});
