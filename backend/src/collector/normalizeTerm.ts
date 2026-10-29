import { AppError } from '../errors.js';

// Reddit's documented rule is 3-21 characters, but a few legacy subreddits (r/de) have 2.
// Only names that can never be valid are rejected here; Reddit decides whether one exists.
const SUBREDDIT_NAME = /^[A-Za-z0-9_]{2,21}$/;
const URL_LIKE = /^(https?:\/\/)?([a-z0-9-]+\.)*reddit\.com(\/|$)/i;

/** Returns the bare lowercase subreddit name, or throws INVALID_TERM. */
export function normalizeTerm(input: string): string {
  const name = extractName(input.trim());
  if (name === null || !SUBREDDIT_NAME.test(name)) {
    throw new AppError('INVALID_TERM');
  }
  return name.toLowerCase();
}

function extractName(term: string): string | null {
  if (URL_LIKE.test(term)) {
    const url = new URL(/^https?:\/\//i.test(term) ? term : `https://${term}`);
    return url.pathname.match(/^\/r\/([^/]+)/i)?.[1] ?? null;
  }
  return term.replace(/^\/?r\//i, '').replace(/\/$/, '');
}
