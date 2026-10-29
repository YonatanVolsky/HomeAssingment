import { act, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { NOW } from '../test/makePost';
import { EmptyState } from './EmptyState';
import { ErrorBanner } from './ErrorBanner';
import { FreshnessBar } from './FreshnessBar';
import { LoadingState } from './LoadingState';

afterEach(() => vi.useRealTimers());

describe('LoadingState', () => {
  it('announces the collection politely', () => {
    render(<LoadingState term="ubisoft" />);
    expect(screen.getByRole('status')).toHaveTextContent('Collecting posts from r/ubisoft');
  });
});

describe('EmptyState', () => {
  it('explains that there are no posts and what to try', () => {
    render(<EmptyState term="quiet" />);
    expect(screen.getByText('No posts found in r/quiet.')).toBeInTheDocument();
    expect(screen.getByText(/check the spelling/i)).toBeInTheDocument();
  });
});

describe('ErrorBanner', () => {
  const timeout = {
    code: 'UPSTREAM_TIMEOUT',
    message: 'Reddit took too long to respond.',
    retryable: true,
  } as const;

  it('shows the message as an alert with a Try again button', async () => {
    const onRetry = vi.fn();
    render(<ErrorBanner error={timeout} onRetry={onRetry} now={NOW} />);

    expect(screen.getByRole('alert')).toHaveTextContent('Reddit took too long to respond.');
    await userEvent.click(screen.getByRole('button', { name: 'Try again' }));
    expect(onRetry).toHaveBeenCalledOnce();
  });

  it('offers no retry and asks for a different input when not retryable', () => {
    render(
      <ErrorBanner
        error={{ code: 'NOT_FOUND_SUBREDDIT', message: 'Not found.', retryable: false }}
        onRetry={vi.fn()}
        now={NOW}
      />,
    );
    expect(screen.queryByRole('button')).not.toBeInTheDocument();
    expect(screen.getByText(/check the name/i)).toBeInTheDocument();
  });

  it('keeps Try again disabled with a countdown until the rate limit passes', () => {
    vi.useFakeTimers();
    const error = {
      code: 'RATE_LIMITED',
      message: 'Slow down.',
      retryable: true,
      retryAfterSeconds: 3,
    } as const;
    render(<ErrorBanner error={error} onRetry={vi.fn()} now={NOW} />);

    expect(screen.getByRole('button', { name: 'Try again in 3 s' })).toBeDisabled();
    act(() => vi.advanceTimersByTime(1000));
    expect(screen.getByRole('button', { name: 'Try again in 2 s' })).toBeDisabled();
    act(() => vi.advanceTimersByTime(2000));
    expect(screen.getByRole('button', { name: 'Try again' })).toBeEnabled();
  });

  it('says when the results shown below were collected', () => {
    render(
      <ErrorBanner
        error={timeout}
        onRetry={vi.fn()}
        now={NOW}
        lastGoodAt="2026-10-29T11:00:00.000Z"
      />,
    );
    expect(screen.getByText('Showing results collected 1 h ago.')).toBeInTheDocument();
  });
});

describe('FreshnessBar', () => {
  const collection = {
    id: 1,
    term: 'ubisoft',
    source: 'live' as const,
    collectedAt: '2026-10-29T11:59:40.000Z',
    postCount: 7,
  };

  it('shows when the feed was collected and a live badge', () => {
    render(
      <FreshnessBar
        collection={collection}
        now={NOW}
        staleAfterSeconds={600}
        collectorMode="live"
      />,
    );

    expect(screen.getByText(/7 posts from r\//)).toHaveTextContent(
      '7 posts from r/ubisoft · collected just now',
    );
    expect(screen.getByText('Live')).toBeInTheDocument();
  });

  it('shows a cached badge for a cached feed', () => {
    render(
      <FreshnessBar
        collection={{ ...collection, source: 'cache' }}
        now={NOW}
        staleAfterSeconds={600}
        collectorMode="live"
      />,
    );
    expect(screen.getByText('Cached')).toBeInTheDocument();
  });

  it('hints to refresh once the feed is older than the stale threshold', () => {
    const old = { ...collection, collectedAt: '2026-10-29T11:40:00.000Z' };
    render(
      <FreshnessBar collection={old} now={NOW} staleAfterSeconds={600} collectorMode="live" />,
    );
    expect(screen.getByText(/may be out of date/i)).toBeInTheDocument();
  });

  it('labels offline sample data in fixture mode', () => {
    render(
      <FreshnessBar
        collection={collection}
        now={NOW}
        staleAfterSeconds={600}
        collectorMode="fixture"
      />,
    );
    expect(screen.getByText(/offline sample data/i)).toBeInTheDocument();
  });
});
