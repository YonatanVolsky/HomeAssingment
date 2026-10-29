import type { Clock } from '../clock.js';
import type { Config } from '../config.js';
import type { Logger } from '../logger.js';
import { DEFAULT_SAMPLE_FILE, FixtureCollector } from './fixtureCollector.js';
import { createAnonymousTokenFetcher, createMobileListingSource } from './reddit/mobileApi.js';
import { RedditCollector } from './redditCollector.js';
import { TokenProvider } from './tokenProvider.js';
import type { Collector } from './types.js';

export function createCollector(config: Config, deps: { clock: Clock; logger: Logger }): Collector {
  if (config.collectorMode === 'fixture') {
    return FixtureCollector.fromFile(DEFAULT_SAMPLE_FILE, deps.clock);
  }
  return new RedditCollector({
    tokens: new TokenProvider(createAnonymousTokenFetcher(config), deps.clock, deps.logger),
    source: createMobileListingSource(config),
    deadlineMs: config.collectionDeadlineMs,
  });
}
