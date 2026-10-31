// The web service: REST routes in front of the inner server, plus the built UI.
import fs from 'node:fs';
import path from 'node:path';
import express from 'express';
import { errorBody, InnerError, statusFor } from './errors.js';

export function createApp({ routes, inner, staticDir }) {
  const app = express();
  app.disable('x-powered-by');

  app.use('/api', (_req, res, next) => {
    res.set('Cache-Control', 'no-store');
    next();
  });

  for (const route of routes) {
    app[route.method](route.path, async (req, res) => {
      try {
        sendReply(res, await inner.send(route.toMessage(req.query)));
      } catch (error) {
        const code = error instanceof InnerError ? error.code : 'INTERNAL';
        res.status(statusFor(code)).json({ error: errorBody(code) });
      }
    });
  }

  app.use('/api', (_req, res) => res.status(404).json({ error: errorBody('NOT_FOUND') }));

  if (staticDir && fs.existsSync(path.join(staticDir, 'index.html'))) {
    serveUi(app, staticDir);
  }
  return app;
}

function sendReply(res, reply) {
  if (reply.ok) {
    res.status(200).json(reply.result);
    return;
  }
  const { error, lastGood } = reply;
  if (typeof error.retryAfterSeconds === 'number') {
    res.set('Retry-After', String(error.retryAfterSeconds));
  }
  res.status(statusFor(error.code)).json({ error, ...(lastGood !== undefined && { lastGood }) });
}

// Files from the build; any other page gets index.html (client-side routes).
// express.static never serves outside its root.
function serveUi(app, staticDir) {
  const root = path.resolve(staticDir);
  app.use(express.static(root, { index: 'index.html' }));
  app.get('/{*page}', (_req, res) => res.sendFile(path.join(root, 'index.html')));
}
