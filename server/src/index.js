// Starts the web service: node src/index.js
import { fileURLToPath } from 'node:url';
import { createApp } from './app.js';
import { ConfigError, loadConfig } from './config.js';
import { createInnerClient } from './innerClient.js';
import { ROUTE_PRESETS } from './routes.js';

const STATIC_DIR = fileURLToPath(new URL('../../frontend/dist', import.meta.url));

let config;
try {
  config = loadConfig(process.env);
} catch (error) {
  if (!(error instanceof ConfigError)) throw error;
  console.error(error.message);
  process.exit(1);
}

const inner = createInnerClient({
  host: config.innerHost,
  port: config.innerPort,
  timeoutMs: config.innerTimeoutMs,
});
const app = createApp({ routes: ROUTE_PRESETS[config.apiRoutes], inner, staticDir: STATIC_DIR });

const server = app.listen(config.port, config.host, () => {
  const { address, port } = server.address();
  console.log(
    `web service listening on http://${address}:${port} ` +
      `(inner server ${config.innerHost}:${config.innerPort})`,
  );
});
server.on('error', (error) => {
  console.error(`web service could not start: ${error.message}`);
  process.exit(1);
});
for (const signal of ['SIGINT', 'SIGTERM'])
  process.on(signal, () => server.close(() => process.exit(0)));
