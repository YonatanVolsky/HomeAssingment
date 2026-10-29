import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { App } from './App';
import { LAST_TERM_KEY } from './lib/lastTerm';
import { makePost } from './test/makePost';

type Handler = (url: string, init?: RequestInit) => Response | Promise<Response>;

const json = (status: number, body: unknown) =>
  new Response(JSON.stringify(body), { status, headers: { 'content-type': 'application/json' } });

const health = (collectorMode = 'live') =>
  json(200, { status: 'ok', db: 'ok', collectorMode, staleAfterSeconds: 600 });

const feed = (posts = [makePost('t3_a', { title: 'First post' })], source = 'live') => ({
  collection: {
    id: 1,
    term: 'ubisoft',
    source,
    collectedAt: new Date().toISOString(),
    postCount: posts.length,
  },
  posts,
});

function serve(handlers: { collect?: Handler; posts?: Handler; health?: Handler }) {
  const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
    if (url === '/api/health') return (handlers.health ?? (() => health()))(url, init);
    if (url.startsWith('/api/posts'))
      return (handlers.posts ?? (() => json(200, { collection: null, posts: [] })))(url, init);
    if (url === '/api/collections' && handlers.collect) return handlers.collect(url, init);
    throw new TypeError('Failed to fetch');
  });
  vi.stubGlobal('fetch', fetchMock);
  return fetchMock;
}

async function search(term: string) {
  await userEvent.type(screen.getByLabelText('Subreddit'), `${term}{Enter}`);
}

beforeEach(() => localStorage.clear());
afterEach(() => vi.unstubAllGlobals());

describe('App', () => {
  it('starts idle with an example', () => {
    serve({});
    render(<App />);
    expect(screen.getByText(/try a subreddit like/i)).toBeInTheDocument();
  });

  it('shows loading, then a feed of cards', async () => {
    let finish!: () => void;
    serve({
      collect: () =>
        new Promise((resolve) => {
          finish = () => resolve(json(200, feed()));
        }),
    });
    render(<App />);

    await search('ubisoft');
    expect(await screen.findByRole('status')).toHaveTextContent('Collecting posts from r/ubisoft');

    finish();
    expect(await screen.findByRole('heading', { name: 'First post' })).toBeInTheDocument();
    expect(screen.getByText('Live')).toBeInTheDocument();
  });

  it('shows the empty state when there are no posts', async () => {
    serve({ collect: () => json(200, feed([])) });
    render(<App />);

    await search('quiet');

    expect(await screen.findByText(/no posts found in r\/ubisoft/i)).toBeInTheDocument();
  });

  it('shows an error next to the last good feed', async () => {
    serve({
      collect: () =>
        json(504, {
          error: {
            code: 'UPSTREAM_TIMEOUT',
            message: 'Reddit took too long to respond.',
            retryable: true,
          },
          lastGood: feed(undefined, 'cache'),
        }),
    });
    render(<App />);

    await search('ubisoft');

    expect(await screen.findByRole('alert')).toHaveTextContent('Reddit took too long to respond.');
    expect(screen.getByRole('heading', { name: 'First post' })).toBeInTheDocument();
  });

  it('explains when the backend cannot be reached', async () => {
    serve({});
    render(<App />);

    await search('ubisoft');

    expect(await screen.findByRole('alert')).toHaveTextContent('Cannot reach the local server');
  });

  it('refreshes the shown subreddit with force', async () => {
    const fetchMock = serve({ collect: () => json(200, feed()) });
    render(<App />);
    await search('ubisoft');
    await screen.findByRole('heading', { name: 'First post' });

    await userEvent.click(screen.getByRole('button', { name: 'Refresh' }));

    const bodies = fetchMock.mock.calls
      .filter(([url]) => url === '/api/collections')
      .map(([, init]) => JSON.parse(String(init?.body)));
    expect(bodies.at(-1)).toEqual({ term: 'ubisoft', force: true });
  });

  it('labels offline sample data in fixture mode', async () => {
    serve({ health: () => health('fixture') });
    render(<App />);
    expect(await screen.findByText(/offline mode/i)).toBeInTheDocument();
  });

  it('restores the last searched subreddit from the database on reload', async () => {
    localStorage.setItem(LAST_TERM_KEY, 'ubisoft');
    const fetchMock = serve({ posts: () => json(200, feed(undefined, 'cache')) });
    render(<App />);

    const list = await screen.findByRole('list', { name: 'Posts' });
    expect(within(list).getByRole('heading', { name: 'First post' })).toBeInTheDocument();
    expect(screen.getByText('Cached')).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith('/api/posts?term=ubisoft', expect.anything());
    expect(screen.getByLabelText('Subreddit')).toHaveValue('ubisoft');
  });
});
