import { relativeTime } from '../lib/format';
export function FreshnessBar({ collection, now, staleAfterSeconds, collectorMode }) {
  const ageSeconds = (now.getTime() - new Date(collection.collectedAt).getTime()) / 1000;
  const badge =
    collectorMode === 'fixture'
      ? { label: 'Offline sample data', className: 'badge sample' }
      : collection.source === 'live'
        ? { label: 'Live', className: 'badge live' }
        : { label: 'Cached', className: 'badge cached' };
  return (
    <div className="freshness">
      <span className={badge.className}>{badge.label}</span>
      <span>
        {collection.postCount} {collection.postCount === 1 ? 'post' : 'posts'} from r/
        {collection.term} · collected{' '}
        <time dateTime={collection.collectedAt}>{relativeTime(collection.collectedAt, now)}</time>
      </span>
      {ageSeconds > staleAfterSeconds && (
        <span className="stale">These results may be out of date. Refresh to collect again.</span>
      )}
    </div>
  );
}
