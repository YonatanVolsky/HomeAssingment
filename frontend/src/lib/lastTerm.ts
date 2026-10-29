export const LAST_TERM_KEY = 'reddit-collector:last-term';

// Storage can be missing or throw (private mode, blocked site data); the app works without it.
export function readLastTerm(): string | null {
  try {
    return localStorage.getItem(LAST_TERM_KEY);
  } catch {
    return null;
  }
}

export function saveLastTerm(term: string): void {
  try {
    localStorage.setItem(LAST_TERM_KEY, term);
  } catch {
    // Not worth surfacing: only the reload convenience is lost.
  }
}
