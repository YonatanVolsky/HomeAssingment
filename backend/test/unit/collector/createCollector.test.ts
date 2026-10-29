import { describe, expect, it } from 'vitest';
import { createCollector } from '../../../src/collector/createCollector.js';
import { FixtureCollector } from '../../../src/collector/fixtureCollector.js';
import { RedditCollector } from '../../../src/collector/redditCollector.js';
import { loadConfig } from '../../../src/config.js';
import { FakeClock, makeLogger } from '../../helpers.js';

const deps = { clock: new FakeClock(), logger: makeLogger().logger };

describe('createCollector', () => {
  it('uses the fixture collector only in fixture mode', () => {
    const collector = createCollector(loadConfig({ COLLECTOR_MODE: 'fixture' }), deps);
    expect(collector).toBeInstanceOf(FixtureCollector);
  });

  it('uses the Reddit collector by default', () => {
    expect(createCollector(loadConfig({}), deps)).toBeInstanceOf(RedditCollector);
  });

  it('explains clearly when live collection is not wired up yet', async () => {
    const collector = createCollector(loadConfig({}), deps);

    await expect(collector.collect('ubisoft', 25)).rejects.toMatchObject({
      code: 'UPSTREAM_ERROR',
      retryable: false,
      message: expect.stringContaining('not available yet'),
    });
  });
});
