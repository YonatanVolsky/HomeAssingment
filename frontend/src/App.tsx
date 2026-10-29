import type { CollectionResponse } from '@reddit-collector/contracts';

const empty: CollectionResponse = { collection: null, posts: [] };

export function App() {
  return <main>Reddit Collector ({empty.posts.length} posts)</main>;
}
