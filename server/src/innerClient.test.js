import net from 'node:net';
import { afterEach, describe, expect, it } from 'vitest';
import { InnerError } from './errors.js';
import { createInnerClient, errorCodeFor } from './innerClient.js';

const servers = [];

// A fake inner server: `onConnection(socket, line)` runs once the first line arrives,
// or immediately with line === null when `immediate` is set.
async function fakeServer(onConnection, { immediate = false } = {}) {
  const server = net.createServer((socket) => {
    if (immediate) return onConnection(socket, null);
    let buffer = '';
    socket.on('data', (data) => {
      buffer += data;
      if (buffer.includes('\n')) onConnection(socket, buffer);
    });
    socket.on('error', () => {});
  });
  await new Promise((resolve) => server.listen(0, '127.0.0.1', resolve));
  servers.push(server);
  return server.address().port;
}

async function closedPort() {
  const server = net.createServer();
  await new Promise((resolve) => server.listen(0, '127.0.0.1', resolve));
  const { port } = server.address();
  await new Promise((resolve) => server.close(resolve));
  return port;
}

afterEach(async () => {
  for (const server of servers.splice(0)) {
    server.closeAllConnections?.();
    await new Promise((resolve) => server.close(resolve));
  }
});

const client = (port, timeoutMs = 2000) =>
  createInnerClient({ host: '127.0.0.1', port, timeoutMs });
const message = { v: 1, command: 'GET', resource: 'health' };

async function expectCode(promise, code) {
  const error = await promise.catch((e) => e);
  expect(error).toBeInstanceOf(InnerError);
  expect(error.code).toBe(code);
}

describe('innerClient.send', () => {
  it('sends one line and resolves with the reply', async () => {
    let received;
    const port = await fakeServer((socket, line) => {
      received = line;
      socket.end('{"ok":true,"result":{"a":1}}\n');
    });
    await expect(client(port).send(message)).resolves.toEqual({ ok: true, result: { a: 1 } });
    expect(received).toBe(JSON.stringify(message) + '\n');
  });

  it('assembles a reply split across packets and ignores bytes after the newline', async () => {
    const port = await fakeServer((socket) => {
      const parts = ['{"ok":tr', 'ue,"result":', '{"a":2}}\ngarbage'];
      parts.forEach((part, i) => setTimeout(() => socket.write(part), i * 20));
    });
    await expect(client(port).send(message)).resolves.toEqual({ ok: true, result: { a: 2 } });
  });

  it('reports INNER_UNAVAILABLE when nothing listens', async () => {
    await expectCode(client(await closedPort()).send(message), 'INNER_UNAVAILABLE');
  });

  it('reports INNER_UNAVAILABLE when the server closes before replying', async () => {
    const port = await fakeServer((socket) => socket.end('{"ok":true'));
    await expectCode(client(port).send(message), 'INNER_UNAVAILABLE');
  });

  it('reports INNER_UNAVAILABLE when the server resets the connection', async () => {
    const port = await fakeServer((socket) => socket.resetAndDestroy());
    await expectCode(client(port).send(message), 'INNER_UNAVAILABLE');
  });

  it('reports UPSTREAM_TIMEOUT when no reply arrives in time', async () => {
    const port = await fakeServer(() => {});
    const started = Date.now();
    await expectCode(client(port, 100).send(message), 'UPSTREAM_TIMEOUT');
    expect(Date.now() - started).toBeLessThan(1000);
  });

  it.each([
    'not json\n',
    '[]\n',
    '{"result":1}\n',
    '{"ok":true}\n',
    '{"ok":false}\n',
    '{"ok":false,"error":{}}\n',
    '{"ok":false,"error":{"code":5,"message":"x","retryable":true}}\n',
    '{"ok":false,"error":{"code":"X","retryable":true}}\n',
    '{"ok":false,"error":{"code":"X","message":"x","retryable":"yes"}}\n',
  ])('reports INTERNAL for %j', async (reply) => {
    const port = await fakeServer((socket) => socket.end(reply));
    await expectCode(client(port).send(message), 'INTERNAL');
  });

  it('accepts an error reply with its optional fields', async () => {
    const reply = {
      ok: false,
      error: { code: 'RATE_LIMITED', message: 'Wait.', retryable: true, retryAfterSeconds: 3 },
      lastGood: null,
    };
    const port = await fakeServer((socket) => socket.end(JSON.stringify(reply) + '\n'));
    await expect(client(port).send(message)).resolves.toEqual(reply);
  });
});

describe('errorCodeFor', () => {
  it.each([
    'ECONNREFUSED',
    'ECONNRESET',
    'EPIPE',
    'ENOTFOUND',
    'EHOSTUNREACH',
    'ENETUNREACH',
    'ETIMEDOUT',
    'EAI_AGAIN',
    'ECONNABORTED',
    'EADDRNOTAVAIL',
  ])('%s means the collector is unavailable', (code) => {
    expect(errorCodeFor(Object.assign(new Error(code), { code }))).toBe('INNER_UNAVAILABLE');
  });

  it('anything else is INTERNAL', () => {
    expect(errorCodeFor(new Error('boom'))).toBe('INTERNAL');
  });
});
