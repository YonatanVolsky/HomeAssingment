import type { FastifyReply } from 'fastify';
import type { CollectionResponse, ErrorResponse } from '@reddit-collector/contracts';
import { type AppError, toErrorBody } from '../errors.js';

export function sendError(reply: FastifyReply, error: AppError, lastGood?: CollectionResponse) {
  if (error.retryAfterSeconds !== undefined) {
    reply.header('retry-after', String(error.retryAfterSeconds));
  }
  const body: ErrorResponse = { error: toErrorBody(error), ...(lastGood && { lastGood }) };
  return reply.code(error.httpStatus).send(body);
}
