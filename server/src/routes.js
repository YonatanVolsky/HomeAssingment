// Route presets: which HTTP request becomes which inner-server command. API_ROUTES picks one.

const PROTOCOL_VERSION = 1;

/** The first of repeated query values (?term=a&term=b → 'a'); never an array. */
export function firstValue(value) {
  return Array.isArray(value) ? value[0] : value;
}

function pick(query, names) {
  const args = {};
  for (const name of names) {
    const value = firstValue(query[name]);
    if (value !== undefined) args[name] = String(value);
  }
  return args;
}

const command = (resource, args) => ({
  v: PROTOCOL_VERSION,
  command: 'GET',
  resource,
  ...(args && { args }),
});

const freeze = (routes) => Object.freeze(routes.map((route) => Object.freeze(route)));

export const ROUTE_PRESETS = Object.freeze({
  rest: freeze([
    {
      method: 'get',
      path: '/api/posts',
      toMessage: (query) => command('posts', pick(query, ['term', 'freshness'])),
    },
    { method: 'get', path: '/api/health', toMessage: () => command('health') },
  ]),
});

export const ROUTE_NAMES = Object.keys(ROUTE_PRESETS);
