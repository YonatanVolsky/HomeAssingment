import type { Post } from '@reddit-collector/contracts';
import type { Collector } from '../src/collector/types.js';
import { openDatabase } from '../src/db/connection.js';
import { createRepository } from '../src/db/repository.js';
import { ensureSchema } from '../src/db/schema.js';
import type { FakeClock } from './helpers.js';
import { makeLogger } from './helpers.js';

/** A collector whose next result the test controls, and which counts its calls. */
export class FakeCollector implements Collector {
  calls: { subreddit: string; limit: number }[] = [];
  next: () => Promise<Post[]> = async () => [];
  private gate: Promise<void> | null = null;
  private release: (() => void) | null = null;

  async collect(subreddit: string, limit: number): Promise<Post[]> {
    this.calls.push({ subreddit, limit });
    if (this.gate) await this.gate;
    return this.next();
  }

  /** Makes the next collections wait until `open()` is called. */
  hold(): void {
    this.gate = new Promise((resolve) => {
      this.release = resolve;
    });
  }

  open(): void {
    this.release?.();
    this.gate = null;
  }
}

export function memoryRepository(clock: FakeClock) {
  const db = openDatabase(':memory:');
  ensureSchema(db);
  const log = makeLogger();
  return { db, repository: createRepository(db, clock, log.logger), log };
}
