import type { CollectionSummary, Post } from '@reddit-collector/contracts';

/** A successful collection as stored. The service decides `source` (live or cache). */
export type StoredCollection = Omit<CollectionSummary, 'source'>;

export interface PostRow {
  reddit_id: string;
  title: string;
  author: string | null;
  comment_count: number;
  score: number;
  created_at: string;
  permalink: string;
  subreddit: string | null;
  preview_text: string | null;
  flair: string | null;
}

export interface CollectionRow {
  id: number;
  term: string;
  post_count: number;
  finished_at: string;
}

export function rowToPost(row: PostRow): Post {
  return {
    id: row.reddit_id,
    title: row.title,
    author: row.author,
    commentCount: row.comment_count,
    score: row.score,
    createdAt: row.created_at,
    permalink: row.permalink,
    subreddit: row.subreddit,
    previewText: row.preview_text,
    flair: row.flair,
  };
}

export function rowToStoredCollection(row: CollectionRow): StoredCollection {
  return {
    id: row.id,
    term: row.term,
    postCount: row.post_count,
    collectedAt: row.finished_at,
  };
}
