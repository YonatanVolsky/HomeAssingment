import type { FastifyInstance } from 'fastify';
import type { HealthResponse } from '@reddit-collector/contracts';
import type { Config } from '../config.js';
import type { CollectionRepository } from '../db/repository.js';

export function healthRoutes(
  app: FastifyInstance,
  deps: { repository: Pick<CollectionRepository, 'ping'>; config: Config },
) {
  app.get('/api/health', async (request, reply) => {
    const base = {
      collectorMode: deps.config.collectorMode,
      staleAfterSeconds: deps.config.staleAfterSeconds,
    };
    try {
      deps.repository.ping();
      const body: HealthResponse = { status: 'ok', db: 'ok', ...base };
      return body;
    } catch (error) {
      request.log.error({ err: error }, 'health check: database unavailable');
      const body: HealthResponse = { status: 'error', db: 'error', ...base };
      return reply.code(503).send(body);
    }
  });
}
