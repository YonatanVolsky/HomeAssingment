// Talks to the inner collector server: one JSON line out, one JSON line back, per connection.
// See docs/inner-protocol.md.
import net from 'node:net';
import { InnerError } from './errors.js';

const MAX_REPLY_BYTES = 1024 * 1024;
const UNAVAILABLE_CODES = new Set(['ECONNREFUSED', 'ECONNRESET', 'EPIPE', 'ENOTFOUND']);

export function createInnerClient({ host, port, timeoutMs }) {
  return { send: (message) => send({ host, port, timeoutMs }, message) };
}

function send({ host, port, timeoutMs }, message) {
  return new Promise((resolve, reject) => {
    const socket = net.createConnection({ host, port });
    const chunks = [];
    let size = 0;
    let settled = false;

    // Exactly one outcome per call; the socket is always destroyed.
    const settle = (outcome) => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      socket.destroy();
      outcome();
    };
    const fail = (code, cause) => settle(() => reject(new InnerError(code, { cause })));
    const timer = setTimeout(() => fail('UPSTREAM_TIMEOUT'), timeoutMs);

    socket.on('connect', () => socket.write(JSON.stringify(message) + '\n'));
    socket.on('data', (data) => {
      const newline = data.indexOf(0x0a);
      chunks.push(newline === -1 ? data : data.subarray(0, newline));
      size += data.length;
      if (newline !== -1) return settle(() => parseReply(Buffer.concat(chunks), resolve, reject));
      if (size > MAX_REPLY_BYTES) fail('INTERNAL');
    });
    socket.on('end', () => fail('INNER_UNAVAILABLE'));
    socket.on('error', (error) =>
      fail(UNAVAILABLE_CODES.has(error.code) ? 'INNER_UNAVAILABLE' : 'INTERNAL', error),
    );
  });
}

function parseReply(line, resolve, reject) {
  let reply;
  try {
    reply = JSON.parse(line.toString('utf8'));
  } catch (cause) {
    return reject(new InnerError('INTERNAL', { cause }));
  }
  const isProtocolReply =
    reply !== null && typeof reply === 'object' && typeof reply.ok === 'boolean';
  return isProtocolReply ? resolve(reply) : reject(new InnerError('INTERNAL'));
}
