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

  if (staticDir) serveUi(app, staticDir);

  // Last: anything Express itself rejects (e.g. a URL that cannot be decoded) gets a JSON
  // error, never the default HTML page with a stack trace.
  app.use((error, _req, res, _next) => {
    const code = error?.status === 400 ? 'INVALID_REQUEST' : 'INTERNAL';
    res.status(statusFor(code)).json({ error: errorBody(code) });
  });
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

const NOT_BUILT =
  'The UI is not built yet. Run "npm run build" and reload, or use "npm run dev" for development.';

// Files from the build; any other page gets index.html (client-side routes).
// express.static never serves outside its root. The build is looked up per request, so
// building while the web service runs needs no restart.
function serveUi(app, staticDir) {
  const root = path.resolve(staticDir);
  const index = path.join(root, 'index.html');
  app.use(express.static(root, { index: 'index.html' }));
  app.get('/{*page}', (_req, res) => {
    if (fs.existsSync(index)) res.sendFile(index);
    else res.status(503).type('text/plain').send(NOT_BUILT);
  });
}
