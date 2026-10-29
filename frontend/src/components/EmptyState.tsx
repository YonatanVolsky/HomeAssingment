export function EmptyState({ term }: { term: string }) {
  return (
    <div className="empty">
      <p className="empty-title">No posts found in r/{term}.</p>
      <p>
        Check the spelling, or try another subreddit. A new or very quiet subreddit may simply have
        no posts yet.
      </p>
    </div>
  );
}
