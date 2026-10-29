import { useEffect, useState } from 'react';
import { relativeTime } from '../lib/format';
const waitFor = (error) => ('retryAfterSeconds' in error ? (error.retryAfterSeconds ?? 0) : 0);

/**
 * @param {object} props
 * @param {import('../api/types').ErrorBody} props.error
 * @param {() => void} props.onRetry
 * @param {Date} props.now
 * @param {string} [props.lastGoodAt]  when the feed shown below the banner was collected
 */
export function ErrorBanner({ error, onRetry, now, lastGoodAt }) {
  const [remaining, setRemaining] = useState(() => waitFor(error));
  const [countedFor, setCountedFor] = useState(error);
  if (countedFor !== error) {
    // A new error (even an identical-looking one after a retry) restarts the countdown.
    setCountedFor(error);
    setRemaining(waitFor(error));
  }
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
