import type { Post } from '@reddit-collector/contracts';
import { PostCard } from './PostCard';

export function PostList({ posts, now }: { posts: Post[]; now: Date }) {
  return (
    <ul className="post-list" aria-label="Posts">
      {posts.map((post) => (
        <li key={post.id}>
          <PostCard post={post} now={now} />
        </li>
      ))}
    </ul>
  );
}
