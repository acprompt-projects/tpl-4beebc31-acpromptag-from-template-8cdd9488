const { RegistryService } = require('./registry-service');

const registry = new RegistryService();

function parseQuery(q, key, type = 'string') {
  const val = q[key];
  if (val === undefined) return undefined;
  if (type === 'int') return parseInt(val, 10);
  if (type === 'array') return Array.isArray(val) ? val : [val];
  return val;
}

function jsonResponse(res, status, body) {
  res.writeHead(status, { 'Content-Type': 'application/json' });
  res.end(JSON.stringify(body));
}

function readBody(req) {
  return new Promise((resolve, reject) => {
    let data = '';
    req.on('data', chunk => { data += chunk; });
    req.on('end', () => { try { resolve(JSON.parse(data)); } catch (e) { reject(e); } });
    req.on('error', reject);
  });
}

async function handleRequest(req, res) {
  const url = new URL(req.url, `http://${req.headers.host || 'localhost'}`);
  const path = url.pathname;
  const method = req.method;
  const q = Object.fromEntries(url.searchParams);

  try {
    if (method === 'POST' && path === '/agents') {
      const body = await readBody(req);
      const agent = registry.register(body);
      return jsonResponse(res, 201, agent);
    }

    if (method === 'GET' && path === '/agents/search') {
      const result = registry.search({
        capability: q.capability,
        capabilities: parseQuery(q, 'capabilities', 'array'),
        availability: q.availability,
        limit: parseQuery(q, 'limit', 'int') || 20,
        offset: parseQuery(q, 'offset', 'int') || 0,
      });
      return jsonResponse(res, 200, result);
    }

    const agentMatch = path.match(/^\/agents\/([^/]+)$/);
    if (agentMatch) {
      const handle = decodeURIComponent(agentMatch[1]);

      if (method === 'GET') {
        const agent = registry.get(handle);
        if (!agent) return jsonResponse(res, 404, { error: 'agent not found' });
        return jsonResponse(res, 200, agent);
      }

      if (method === 'PUT') {
        const body = await readBody(req);
        const agent = registry.update(handle, body);
        if (!agent) return jsonResponse(res, 404, { error: 'agent not found' });
        return jsonResponse(res, 200, agent);
      }

      if (method === 'DELETE') {
        const removed = registry.remove(handle);
        if (!removed) return jsonResponse(res, 404, { error: 'agent not found' });
        return jsonResponse(res, 200, { deleted: true, handle });
      }
    }

    if (method === 'GET' && path === '/agents') {
      const result = registry.list({
        capability: q.capability,
        availability: q.availability,
        limit: parseQuery(q, 'limit', 'int') || 20,
        offset: parseQuery(q, 'offset', 'int') || 0,
      });
      return jsonResponse(res, 200, result);
    }

    return jsonResponse(res, 404, { error: 'route not found' });
  } catch (err) {
    const status = err.message.includes('already registered') ? 409 : 400;
    return jsonResponse(res, status, { error: err.message });
  }
}

function createServer(http) {
  return http.createServer(handleRequest);
}

module.exports = { handleRequest, createServer, registry };