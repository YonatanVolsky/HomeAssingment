import { useEffect, useState } from 'react';
import { DEFAULT_HEALTH, getFeed, getHealth } from './api/client';
import { EmptyState } from './components/EmptyState';
import { ErrorBanner } from './components/ErrorBanner';
import { FreshnessBar } from './components/FreshnessBar';
import { LoadingState } from './components/LoadingState';
import { PostList } from './components/PostList';
import { SearchForm } from './components/SearchForm';
import { readLastTerm, saveLastTerm } from './lib/lastTerm';
import { useNow } from './lib/useNow';
import { visibleFeed } from './state/collectionReducer';
import { useCollection } from './state/useCollection';
// About 10 s at the client's 500 ms interval.
const STARTUP_HEALTH_ATTEMPTS = 20;

export function App() {
  const { view, submit, retry, restore } = useCollection();
  const [health, setHealth] = useState(DEFAULT_HEALTH);
  const [initialTerm] = useState(() => readLastTerm() ?? '');
  const now = useNow();
  useEffect(() => {
    const controller = new AbortController();
    const { signal } = controller;
    // The page may open before the collector is up (npm run dev starts all three at once),
    // so health is retried, and the last search is restored once the collector answers.
    void getHealth({ signal, attempts: STARTUP_HEALTH_ATTEMPTS }).then((current) => {
      if (signal.aborted) return;
      setHealth(current);
      if (!initialTerm) return;
      getFeed(initialTerm, 'stored', { signal }).then(restore, () => {
        // Restoring is a convenience; the user can still search.
      });
    });
    return () => controller.abort();
  }, [initialTerm, restore]);
  const feed = visibleFeed(view);
  const loading = view.kind === 'loading';
  const shownTerm = feed?.collection?.term;
  const search = (term) => {
    saveLastTerm(term);
    submit(term, false);
  };
  return (
    <div className="page">
      <header className="page-header">
        <h1>Reddit Collector</h1>
        <p>Collect the newest posts of a subreddit, stored locally.</p>
      </header>

      {health.collectorMode === 'fixture' && (
        <p className="notice" role="note">
          Offline mode: showing bundled sample data, not live Reddit posts.
        </p>
      )}

      <SearchForm
        onSubmit={search}
        loading={loading}
        initialTerm={initialTerm}
        {...(shownTerm && { onRefresh: () => submit(shownTerm, true) })}
      />

      <main className="results">
        {view.kind === 'idle' && (
          <p className="idle-hint">Try a subreddit like r/ubisoft to see its newest posts.</p>
        )}
        {view.kind === 'loading' && <LoadingState term={view.term.replace(/^\/?r\//i, '')} />}
        {view.kind === 'error' && (
          <ErrorBanner
            error={view.error}
            onRetry={retry}
            now={now}
            {...(view.lastGood?.collection && { lastGoodAt: view.lastGood.collection.collectedAt })}
          />
        )}
        {feed && <Feed feed={feed} view={view.kind} now={now} health={health} />}
      </main>
    </div>
  );
}

function Feed({ feed, view, now, health }) {
  if (!feed.collection) return null;
  return (
    <section className={view === 'loading' ? 'feed dimmed' : 'feed'} aria-busy={view === 'loading'}>
      <FreshnessBar
        collection={feed.collection}
        now={now}
        staleAfterSeconds={health.staleAfterSeconds}
        collectorMode={health.collectorMode}
      />
      {feed.posts.length > 0 ? (
        <PostList posts={feed.posts} now={now} />
      ) : (
        view === 'empty' && <EmptyState term={feed.collection.term} />
      )}
    </section>
  );
}
