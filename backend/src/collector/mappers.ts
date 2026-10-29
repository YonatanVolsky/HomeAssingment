import { AppError } from '../errors.js';

const PREVIEW_MAX = 300;
// Reddit pads empty paragraphs with zero-width spaces, raw or as an HTML entity.
const ZERO_WIDTH = new RegExp('&#x200B;|\\u200B', 'gi');
// Epoch values below this are seconds; above it, milliseconds (year 5138 in seconds).
const MS_THRESHOLD = 1e11;

const contractError = (message: string) =>
  new AppError('CONTRACT_ERROR', undefined, { cause: new Error(message) });

/** Accepts epoch seconds, epoch milliseconds or an ISO string; returns ISO UTC. */
export function toIsoUtc(value: unknown): string {
  const date =
    typeof value === 'number'
      ? fromEpoch(value)
      : typeof value === 'string' && /^\d+(\.\d+)?$/.test(value)
        ? fromEpoch(Number(value))
        : typeof value === 'string'
          ? new Date(value)
          : null;
  if (date === null || Number.isNaN(date.getTime())) {
    throw contractError(`invalid timestamp: ${typeof value}`);
  }
  return date.toISOString();
}

function fromEpoch(value: number): Date | null {
  if (!Number.isFinite(value) || value < 0) return null;
  return new Date(value >= MS_THRESHOLD ? value : value * 1000);
}

/** Absolute https reddit.com URL without query or fragment, or CONTRACT_ERROR. */
export function toAbsolutePermalink(value: unknown): string {
  if (typeof value !== 'string' || value === '') throw contractError('missing permalink');
  let url: URL;
  try {
    url = new URL(value, 'https://www.reddit.com');
  } catch {
    throw contractError('unparseable permalink');
  }
  const host = url.hostname.toLowerCase();
  const isReddit = host === 'reddit.com' || host.endsWith('.reddit.com');
  if (!isReddit || (url.protocol !== 'https:' && url.protocol !== 'http:')) {
    throw contractError('permalink is not a reddit.com URL');
  }
  url.protocol = 'https:';
  url.search = '';
  url.hash = '';
  return url.toString();
}

/** Plain-text preview of at most 300 characters, or null when there is no text. */
export function truncatePreview(value: unknown): string | null {
  if (typeof value !== 'string') return null;
  const text = stripMarkup(value).replace(/\s+/g, ' ').trim();
  if (text === '') return null;
  if (text.length <= PREVIEW_MAX) return text;
  const cut = text.slice(0, PREVIEW_MAX - 1);
  const lastSpace = cut.lastIndexOf(' ');
  const base = lastSpace > PREVIEW_MAX / 2 ? cut.slice(0, lastSpace) : cut;
  return `${base.trimEnd()}…`;
}

function stripMarkup(text: string): string {
  return text
    .replace(/<[^>]+>/g, '')
    .replace(/\[([^\]]*)\]\([^)]*\)/g, '$1')
    .replace(/^#{1,6}\s*/gm, '')
    .replace(/^>\s?/gm, '')
    .replace(/(\*\*|__|~~)(.+?)\1/g, '$2')
    .replace(/(^|\W)[*_](\S(?:.*?\S)?)[*_](?=\W|$)/g, '$1$2')
    .replace(/`([^`]*)`/g, '$1')
    .replace(ZERO_WIDTH, '')
    .replace(/&nbsp;/g, ' ')
    .replace(/&lt;/g, '<')
    .replace(/&gt;/g, '>')
    .replace(/&quot;/g, '"')
    .replace(/&#39;/g, "'")
    .replace(/&amp;/g, '&');
}

const MISSING_AUTHORS = new Set(['', '[deleted]', '[removed]']);

export function mapAuthor(value: unknown): string | null {
  return typeof value === 'string' && !MISSING_AUTHORS.has(value.trim()) ? value.trim() : null;
}

export function mapFlair(value: unknown): string | null {
  return typeof value === 'string' && value.trim() !== '' ? value.trim() : null;
}
