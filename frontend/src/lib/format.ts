const MINUTE = 60;
const HOUR = 60 * MINUTE;
const DAY = 24 * HOUR;

const dateFormat = new Intl.DateTimeFormat('en-US', {
  month: 'short',
  day: 'numeric',
  year: 'numeric',
  timeZone: 'UTC',
});

/** "just now", "49 min ago", "3 h ago", "2 d ago", then a date after 30 days. */
export function relativeTime(iso: string, now: Date): string {
  const date = new Date(iso);
  const seconds = Math.floor((now.getTime() - date.getTime()) / 1000);
  if (seconds < 45) return 'just now';
  if (seconds < HOUR) return `${Math.max(1, Math.round(seconds / MINUTE))} min ago`;
  if (seconds < DAY) return `${Math.floor(seconds / HOUR)} h ago`;
  if (seconds < 30 * DAY) return `${Math.floor(seconds / DAY)} d ago`;
  return dateFormat.format(date);
}

/** 1234 → "1.2k", 1250000 → "1.3M"; exact below 1000. */
export function formatCount(value: number): string {
  const abs = Math.abs(value);
  if (abs < 1000) return String(value);
  const [divisor, suffix] = abs < 1_000_000 ? [1000, 'k'] : [1_000_000, 'M'];
  const scaled = (value / divisor).toFixed(1).replace(/\.0$/, '');
  return `${scaled}${suffix}`;
}

/** Only https links to reddit.com or its subdomains are rendered. */
export function isSafeRedditUrl(url: string): boolean {
  try {
    const parsed = new URL(url);
    const host = parsed.hostname.toLowerCase();
    return parsed.protocol === 'https:' && (host === 'reddit.com' || host.endsWith('.reddit.com'));
  } catch {
    return false;
  }
}
