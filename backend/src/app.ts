import { existsSync } from 'node:fs';
import fastifyStatic from '@fastify/static';
import Fastify, { type FastifyInstance, type FastifyServerOptions } from 'fastify';
import type { Clock } from './clock.js';
import type { Collector } from './collector/types.js';
import type { Config } from './config.js';
import type { CollectionRepository } from './db/repository.js';
import { AppError } from './errors.js';
import { collectionRoutes } from './routes/collections.js';
import { sendError } from './routes/errorReply.js';
import { healthRoutes } from './routes/health.js';
import { CollectionService } from './services/collectionService.js';

export interface AppDeps {
  repository: CollectionRepository;
  collector: Collector;
  clock: Clock;
  config: Config;
  logger?: FastifyServerOptions['logger'];
  /** Built frontend to serve at `/` (production-like run). Skipped when missing. */
  staticDir?: string;
}

const BODY_LIMIT_BYTES = 1024;

export const REDACTED_LOG_PATHS = [
  'req.headers.authorization',
  'req.headers.cookie',
  'headers.authorization',
  'headers.cookie',
  '*.token',
  '*.accessToken',
  '*.access_token',
];

/** Builds the HTTP app from injected dependencies, so tests need no network and no port. */
export async function buildApp(deps: AppDeps): Promise<FastifyInstance> {
  const app = Fastify({
    logger: deps.logger ?? false,
    bodyLimit: BODY_LIMIT_BYTES,
  });

  const service = new CollectionService({
    repository: deps.repository,
    collector: deps.collector,
    clock: deps.clock,
    config: deps.config,
    logger: app.log,
  });

  app.setErrorHandler((error, request, reply) => {
    if (error instanceof AppError) return sendError(reply, error);
    const status = (error as { statusCode?: number }).statusCode;
    if (status !== undefined && status >= 400 && status < 500) {
      // Malformed JSON, oversized body, wrong content type: the request itself is unusable.
      return sendError(reply, new AppError('INVALID_TERM', undefined, { cause: error }));
    }
    request.log.error({ err: error }, 'unhandled error');
    return sendError(reply, new AppError('INTERNAL', undefined, { cause: error }));
  });

  healthRoutes(app, deps);
  collectionRoutes(app, { service });

  if (deps.staticDir && existsSync(deps.staticDir)) {
    await app.register(fastifyStatic, { root: deps.staticDir });
    app.setNotFoundHandler((request, reply) =>
      request.url.startsWith('/api/')
        ? reply.code(404).send({ message: 'Not found' })
        : reply.sendFile('index.html'),
    );
  }

  return app;
}
