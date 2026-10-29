import { isAbsolute, resolve } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { buildApp, REDACTED_LOG_PATHS } from './app.js';
import { systemClock } from './clock.js';
import { createCollector } from './collector/createCollector.js';
import { loadConfig } from './config.js';
import { openDatabase } from './db/connection.js';
import { createRepository } from './db/repository.js';
import { ensureSchema } from './db/schema.js';
import type { Logger } from './logger.js';

// Same location from src/ (tsx) and dist/ (built), so relative paths mean "from the repo root".
const REPO_ROOT = fileURLToPath(new URL('../../', import.meta.url));

export interface RunningServer {
  url: string;
  close(): Promise<void>;
}

export async function startServer(env: Record<string, string | undefined>): Promise<RunningServer> {
  const config = loadConfig(env);
  const dbPath = isAbsolute(config.dbPath) ? config.dbPath : resolve(REPO_ROOT, config.dbPath);
  const db = openDatabase(dbPath);
  ensureSchema(db);

  // Modules log through Fastify's logger, which exists only once the app is built.
  const log: Logger = {
    error: (obj, msg) => app.log.error(obj, msg),
    warn: (obj, msg) => app.log.warn(obj, msg),
    info: (obj, msg) => app.log.info(obj, msg),
  };
  const app = await buildApp({
    config,
    clock: systemClock,
    repository: createRepository(db, systemClock, log),
    collector: createCollector(config, {
      clock: systemClock,
      logger: log,
    }),
    logger: { level: config.logLevel, redact: REDACTED_LOG_PATHS },
    staticDir: resolve(REPO_ROOT, 'frontend/dist'),
  });

  try {
    await app.listen({ host: config.host, port: config.port });
  } catch (error) {
    db.close();
    throw error;
  }
  const address = app.server.address();
  const port = typeof address === 'object' && address ? address.port : config.port;
  app.log.info({ dbPath, collectorMode: config.collectorMode }, 'reddit collector ready');

  return {
    url: `http://${config.host}:${port}`,
    close: async () => {
      await app.close();
      db.close();
    },
  };
}

async function main() {
  let server: RunningServer;
  try {
    server = await startServer(process.env);
  } catch (error) {
    console.error(error instanceof Error ? error.message : error);
    process.exit(1);
  }
  console.log(`Backend listening on ${server.url}`);
  const shutdown = () => {
    server.close().then(
      () => process.exit(0),
      () => process.exit(1),
    );
  };
  process.once('SIGINT', shutdown);
  process.once('SIGTERM', shutdown);
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  void main();
}
