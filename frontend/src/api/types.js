/**
 * The JSON shapes the backend sends (see backend/app/contracts.py). Documentation only:
 * nothing here runs, but editors use these for autocompletion.
 *
 * @typedef {object} Post
 * @property {string} id               Reddit fullname, e.g. "t3_abc123"
 * @property {string} title
 * @property {string | null} author    null for deleted or anonymous authors
 * @property {number} commentCount
 * @property {number} score            may be negative
 * @property {string} createdAt        ISO 8601 UTC
 * @property {string} permalink        absolute https://www.reddit.com/... URL
 * @property {string | null} subreddit
 * @property {string | null} previewText  plain text, at most 300 characters
 * @property {string | null} flair
 *
 * @typedef {object} CollectionSummary  always a successful run
 * @property {number} id
 * @property {string} term
 * @property {'live' | 'cache'} source  "cache" means served from the database
 * @property {string} collectedAt
 * @property {number} postCount
 *
 * @typedef {object} CollectionResponse
 * @property {CollectionSummary | null} collection  null only when a term was never collected
 * @property {Post[]} posts                          newest first
 *
 * @typedef {object} ErrorBody
 * @property {string} code               e.g. "UPSTREAM_TIMEOUT", or "NETWORK" (client only)
 * @property {string} message            safe to show
 * @property {boolean} retryable         whether to offer "Try again"
 * @property {number} [retryAfterSeconds]  only for rate limits
 *
 * @typedef {object} Health
 * @property {'ok' | 'error'} status
 * @property {'ok' | 'error'} db
 * @property {'live' | 'fixture'} collectorMode
 * @property {number} staleAfterSeconds
 */

export {};
