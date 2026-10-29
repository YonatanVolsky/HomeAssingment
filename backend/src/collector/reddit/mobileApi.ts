import type { Config } from '../../config.js';
import { AppError } from '../../errors.js';
import type { ListingSource } from '../redditCollector.js';
import type { TokenFetcher } from '../tokenProvider.js';

// The Reddit mobile app's token and listing requests. They are filled in from the
// traffic capture (docs/reddit-mobile-request.md); until then live mode explains itself.
/** False until the captured requests replace the placeholders below. */
export const LIVE_COLLECTION_AVAILABLE = false;

const notCapturedYet = () =>
  new AppError(
    'UPSTREAM_ERROR',
    'Live Reddit collection is not available yet. Run with COLLECTOR_MODE=fixture for sample data.',
    { autoRetry: false, retryable: false },
  );

export function createAnonymousTokenFetcher(_config: Config): TokenFetcher {
  return async () => ({ accessToken: 'placeholder', expiresInSeconds: 3600 });
}

export function createMobileListingSource(_config: Config): ListingSource {
  return {
    async fetchNewPosts() {
      throw notCapturedYet();
    },
  };
}
