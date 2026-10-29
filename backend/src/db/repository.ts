import type { Database } from 'better-sqlite3';
import type { Post } from '@reddit-collector/contracts';
import type { Clock } from '../clock.js';
import type { Logger } from '../logger.js';
import { type PostRow, rowToPost, type StoredCollection } from './rows.js';

export interface CollectionRepository {
  /** Stores a successful run atomically: posts, the run, and its links. */
  recordSuccess(term: string, posts: Post[], startedAt: Date): StoredCollection;
  getFeed(collectionId: number): Post[];
}

export function createRepository(
  db: Database,
  clock: Clock,
  _logger: Logger,
): CollectionRepository {
  const upsertPost = db.prepare<PostRow & { seen_at: string }, { id: number }>(`
    INSERT INTO posts (reddit_id, title, author, comment_count, score, created_at, permalink,
                       subreddit, preview_text, flair, first_seen_at, last_seen_at)
    VALUES (@reddit_id, @title, @author, @comment_count, @score, @created_at, @permalink,
            @subreddit, @preview_text, @flair, @seen_at, @seen_at)
    ON CONFLICT (reddit_id) DO UPDATE SET
      title = excluded.title,
      author = excluded.author,
      comment_count = excluded.comment_count,
      score = excluded.score,
      permalink = excluded.permalink,
      subreddit = excluded.subreddit,
      preview_text = excluded.preview_text,
      flair = excluded.flair,
      last_seen_at = excluded.last_seen_at
    RETURNING id
  `);
  const insertCollection = db.prepare<
    {
      term: string;
      status: string;
      post_count: number;
      error_code: string | null;
      started_at: string;
      finished_at: string;
    },
    { id: number }
  >(`
    INSERT INTO collections (term, status, post_count, error_code, started_at, finished_at)
    VALUES (@term, @status, @post_count, @error_code, @started_at, @finished_at)
    RETURNING id
  `);
  const insertLink = db.prepare<{ collection_id: number; post_id: number; position: number }>(`
    INSERT OR IGNORE INTO collection_posts (collection_id, post_id, position)
    VALUES (@collection_id, @post_id, @position)
  `);
  const selectFeed = db.prepare<{ collection_id: number }, PostRow>(`
    SELECT p.reddit_id, p.title, p.author, p.comment_count, p.score, p.created_at, p.permalink,
           p.subreddit, p.preview_text, p.flair
    FROM collection_posts cp
    JOIN posts p ON p.id = cp.post_id
    WHERE cp.collection_id = @collection_id
    ORDER BY p.created_at DESC, p.reddit_id ASC
  `);

  const recordSuccessTx = db.transaction(
    (term: string, posts: Post[], startedAt: Date): StoredCollection => {
      const finishedAt = clock.now().toISOString();
      const unique = [...new Map(posts.map((post) => [post.id, post])).values()];
      const collection = insertCollection.get({
        term,
        status: 'success',
        post_count: unique.length,
        error_code: null,
        started_at: startedAt.toISOString(),
        finished_at: finishedAt,
      })!;
      unique.forEach((post, position) => {
        const { id: postId } = upsertPost.get({ ...postToRow(post), seen_at: finishedAt })!;
        insertLink.run({ collection_id: collection.id, post_id: postId, position });
      });
      return { id: collection.id, term, postCount: unique.length, collectedAt: finishedAt };
    },
  );

  return {
    recordSuccess: (term, posts, startedAt) => recordSuccessTx(term, posts, startedAt),
    getFeed: (collectionId) => selectFeed.all({ collection_id: collectionId }).map(rowToPost),
  };
}

function postToRow(post: Post): PostRow {
  return {
    reddit_id: post.id,
    title: post.title,
    author: post.author,
    comment_count: post.commentCount,
    score: post.score,
    created_at: post.createdAt,
    permalink: post.permalink,
    subreddit: post.subreddit,
    preview_text: post.previewText,
    flair: post.flair,
  };
}
