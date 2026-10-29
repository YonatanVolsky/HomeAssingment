import type { Post } from '@reddit-collector/contracts';
import { formatCount, isSafeRedditUrl, relativeTime } from '../lib/format';
import { Icon } from './Icon';

const plural = (count: number, word: string) => `${count} ${word}${count === 1 ? '' : 's'}`;

export function PostCard({ post, now }: { post: Post; now: Date }) {
  const safeLink = isSafeRedditUrl(post.permalink);
  return (
    <article className="card">
      <header className="card-meta">
        <span className={post.author ? 'author' : 'author deleted'}>
          {post.author ? `u/${post.author}` : '[deleted]'}
        </span>
        {post.subreddit && <span>r/{post.subreddit}</span>}
        <time dateTime={post.createdAt} title={new Date(post.createdAt).toLocaleString()}>
          {relativeTime(post.createdAt, now)}
        </time>
      </header>

      <h3 className="card-title">{post.title}</h3>
      {post.flair && <span className="flair">{post.flair}</span>}
      {post.previewText && <p className="card-preview">{post.previewText}</p>}

      <footer className="card-footer">
        <span className="stat">
          <Icon name="arrowUp" />
          <span aria-hidden="true">{formatCount(post.score)}</span>
          <span className="visually-hidden">{plural(post.score, 'point')}</span>
        </span>
        <span className="stat">
          <Icon name="comment" />
          <span aria-hidden="true">{formatCount(post.commentCount)}</span>
          <span className="visually-hidden">{plural(post.commentCount, 'comment')}</span>
        </span>
        {safeLink && (
          <a className="open-link" href={post.permalink} target="_blank" rel="noopener noreferrer">
            Open on Reddit <Icon name="external" />
            <span className="visually-hidden"> (opens in a new tab)</span>
          </a>
        )}
      </footer>
    </article>
  );
}
