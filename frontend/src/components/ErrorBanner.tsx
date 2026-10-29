import { useEffect, useState } from 'react';
import type { UiErrorBody } from '../api/client';
import { relativeTime } from '../lib/format';

interface Props {
  error: UiErrorBody;
  onRetry: () => void;
  now: Date;
  /** When the feed shown below the banner was collected. */
  lastGoodAt?: string;
}

/** Remount (via `key`) for each new error so the countdown restarts. */
export function ErrorBanner({ error, onRetry, now, lastGoodAt }: Props) {
  const waitSeconds = 'retryAfterSeconds' in error ? (error.retryAfterSeconds ?? 0) : 0;
  const [remaining, setRemaining] = useState(waitSeconds);

  const counting = remaining > 0;

  useEffect(() => {
    if (!counting) return;
    const timer = setInterval(() => setRemaining((value) => Math.max(0, value - 1)), 1000);
    return () => clearInterval(timer);
  }, [counting]);

  return (
    <div className="error-banner" role="alert">
      <p className="error-message">{error.message}</p>
      {!error.retryable && <p>Check the name and try a different subreddit.</p>}
      {lastGoodAt && (
        <p className="error-note">Showing results collected {relativeTime(lastGoodAt, now)}.</p>
      )}
      {error.retryable && (
        <button
          type="button"
          className="button secondary"
          onClick={onRetry}
          disabled={remaining > 0}
        >
          {remaining > 0 ? `Try again in ${remaining} s` : 'Try again'}
        </button>
      )}
    </div>
  );
}
