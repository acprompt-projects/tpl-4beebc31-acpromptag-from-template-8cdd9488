const assert = require('assert');
const { handleRequest, registry } = require('../src/api-routes');

function mockRes() {
  const r = { statusCode: 0, body: null, headers: {} };
  r.writeHead = (s, h) => { r.statusCode = s; r.headers = h; };
  r.end = (d) => { r.body = JSON.parse(d); };
  return r;
}

function mockReq(method, path, query = '', body = null) {
  const url = query ? `${path}?${query}` : path;
  return {
    method, url, headers: { host: 'localhost' },
    on(evt, fn) {
      if (evt === 'data' && body) fn(Buffer.from(JSON.stringify(body)));
      if (evt === 'end') fn();
    },
  };
}

async function call(method, path, query, body) {
  const req = mockReq(method, path, query, body);
  const res = mockRes();
  await handleRequest(req, res);
  return res;
}

(async () => {
  // POST /agents - register
  let res = await call('POST', '/agents', null, { handle: 'alpha', capabilities: ['search', 'index'], availability: 'available' });
  assert.strictEqual(res.statusCode, 201);
  assert.strictEqual(res.body.handle, 'alpha');

  // POST /agents - duplicate
  res = await call('POST', '/agents', null, { handle: 'alpha', capabilities: ['x'] });
  assert.strictEqual(res.statusCode, 409);

  // POST /agents - second agent
  await call('POST', '/agents', null, { handle: 'beta', capabilities: ['search', 'translate'], availability: 'busy' });

  // GET /agents/{handle}
  res = await call('GET', '/agents/alpha');
  assert.strictEqual(res.statusCode, 200);
  assert.deepStrictEqual(res.body.capabilities, ['search', 'index']);

  // GET /agents - list all
  res = await call('GET', '/agents');
  assert.strictEqual(res.statusCode, 200);
  assert.strictEqual(res.body.pagination.total, 2);

  // GET /agents?capability=search
  res = await call('GET', '/agents', 'capability=search');
  assert.strictEqual(res.body.pagination.total, 2);

  // GET /agents?availability=busy
  res = await call('GET', '/agents', 'availability=busy');
  assert.strictEqual(res.body.pagination.total, 1);
  assert.strictEqual(res.body.agents[0].handle, 'beta');

  // GET /agents/search?capability=search
  res = await call('GET', '/agents/search', 'capability=search');
  assert.strictEqual(res.statusCode, 200);
  assert.strictEqual(res.body.pagination.total, 2);

  // GET /agents with pagination
  res = await call('GET', '/agents', 'limit=1&offset=0');
  assert.strictEqual(res.body.agents.length, 1);

  // PUT /agents/{handle}
  res = await call('PUT', '/agents/alpha', null, { availability: 'offline', metadata: { region: 'us' } });
  assert.strictEqual(res.statusCode, 200);
  assert.strictEqual(res.body.availability, 'offline');
  assert.strictEqual(res.body.metadata.region, 'us');

  // DELETE /agents/{handle}
  res = await call('DELETE', '/agents/beta');
  assert.strictEqual(res.statusCode, 200);
  assert.strictEqual(res.body.deleted, true);

  // GET /agents/beta - gone
  res = await call('GET', '/agents/beta');
  assert.strictEqual(res.statusCode, 404);

  // 404 route
  res = await call('GET', '/unknown');
  assert.strictEqual(res.statusCode, 404);

  console.log('All tests passed ✓');
})();