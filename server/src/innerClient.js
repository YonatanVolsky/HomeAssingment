// Talks to the inner collector server: one JSON line out, one JSON line back, per connection.
// See docs/inner-protocol.md.
import net from 'node:net';
import { InnerError } from './errors.js';

const MAX_REPLY_BYTES = 1024 * 1024;
// Socket errors that mean the collector cannot be reached (rather than a bug here).
const UNAVAILABLE_CODES = new Set([
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
]);

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
    socket.on('error', (error) => fail(errorCodeFor(error), error));
  });
}

export function errorCodeFor(error) {
  return UNAVAILABLE_CODES.has(error?.code) ? 'INNER_UNAVAILABLE' : 'INTERNAL';
}

function parseReply(line, resolve, reject) {
  let reply;
  try {
    reply = JSON.parse(line.toString('utf8'));
  } catch (cause) {
    return reject(new InnerError('INTERNAL', { cause }));
  }
  return isProtocolReply(reply) ? resolve(reply) : reject(new InnerError('INTERNAL'));
}

// The shapes of docs/inner-protocol.md; app.js relies on them.
function isProtocolReply(reply) {
  if (!isObject(reply)) return false;
  if (reply.ok === true) return 'result' in reply;
  if (reply.ok !== false || !isObject(reply.error)) return false;
  const { code, message, retryable } = reply.error;
  return typeof code === 'string' && typeof message === 'string' && typeof retryable === 'boolean';
}

function isObject(value) {
  return value !== null && typeof value === 'object' && !Array.isArray(value);
}
