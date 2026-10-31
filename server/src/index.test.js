import { spawn } from 'node:child_process';
import net from 'node:net';
import { fileURLToPath } from 'node:url';
import { afterEach, describe, expect, it } from 'vitest';

const INDEX = fileURLToPath(new URL('./index.js', import.meta.url));
const children = [];

afterEach(() => {
  for (const child of children.splice(0)) child.kill();
});

async function freePort() {
  const server = net.createServer();
  await new Promise((resolve) => server.listen(0, '127.0.0.1', resolve));
  const { port } = server.address();
  await new Promise((resolve) => server.close(resolve));
  return port;
}

function start(env) {
  const child = spawn(process.execPath, [INDEX], { env: { ...process.env, ...env } });
  children.push(child);
  let stderr = '';
  child.stderr.on('data', (data) => (stderr += data));
  const exited = new Promise((resolve) => child.on('exit', (code) => resolve({ code, stderr })));
  return { child, exited };
}

describe('node src/index.js', () => {
  it('starts and answers health as 503 when the inner server is down', async () => {
    const port = await freePort();
    start({ PORT: String(port), INNER_PORT: String(await freePort()) });
    let response;
    for (let i = 0; i < 50 && !response; i++) {
      response = await fetch(`http://127.0.0.1:${port}/api/health`).catch(() => undefined);
      if (!response) await new Promise((resolve) => setTimeout(resolve, 100));
    }
    expect(response.status).toBe(503);
    expect((await response.json()).error.code).toBe('INNER_UNAVAILABLE');
  });

  it('refuses invalid configuration', async () => {
    const { exited } = start({ PORT: 'abc' });
    const { code, stderr } = await exited;
    expect(code).toBe(1);
    expect(stderr).toContain('Invalid configuration: PORT');
  });
});
