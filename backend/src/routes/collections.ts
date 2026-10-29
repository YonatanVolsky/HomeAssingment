import type { FastifyInstance } from 'fastify';
import { z } from 'zod';
import { AppError } from '../errors.js';
import type { CollectionService } from '../services/collectionService.js';
import { sendError } from './errorReply.js';

const CollectRequestSchema = z.object({
  term: z.string().min(1).max(200),
  force: z.boolean().optional(),
});

export function collectionRoutes(app: FastifyInstance, deps: { service: CollectionService }) {
  app.post('/api/collections', async (request, reply) => {
    const parsed = CollectRequestSchema.safeParse(request.body);
    if (!parsed.success) throw new AppError('INVALID_TERM');
    const { term, force = false } = parsed.data;
    try {
      return await deps.service.collect(term, force);
    } catch (error) {
      if (!(error instanceof AppError) || error.code === 'INVALID_TERM') throw error;
      request.log.warn({ err: error, term }, 'collection failed');
      return sendError(reply, error, deps.service.lastGood(term));
    }
  });

  app.get('/api/posts', async (request) => {
    const term = (request.query as { term?: unknown }).term;
    if (typeof term !== 'string' || term.length > 200) throw new AppError('INVALID_TERM');
    return deps.service.getPosts(term);
  });
}
