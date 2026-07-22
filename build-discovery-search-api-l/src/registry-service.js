class RegistryService {
  constructor() {
    this.agents = new Map();
    this.collabHistory = [];
  }

  register(data) {
    if (!data.handle || !data.capabilities) throw new Error('handle and capabilities required');
    if (this.agents.has(data.handle)) throw new Error(`agent "${data.handle}" already registered`);
    const agent = {
      handle: data.handle,
      capabilities: data.capabilities,
      availability: data.availability || 'available',
      metadata: data.metadata || {},
      registeredAt: new Date().toISOString(),
      updatedAt: new Date().toISOString(),
    };
    this.agents.set(data.handle, agent);
    return agent;
  }

  get(handle) {
    return this.agents.get(handle) || null;
  }

  update(handle, data) {
    const agent = this.agents.get(handle);
    if (!agent) return null;
    const { capabilities, availability, metadata } = data;
    if (capabilities) agent.capabilities = capabilities;
    if (availability) agent.availability = availability;
    if (metadata) agent.metadata = { ...agent.metadata, ...metadata };
    agent.updatedAt = new Date().toISOString();
    return agent;
  }

  remove(handle) {
    return this.agents.delete(handle);
  }

  list({ capability, availability, limit = 20, offset = 0 } = {}) {
    let results = Array.from(this.agents.values());
    if (capability) results = results.filter(a => a.capabilities.includes(capability));
    if (availability) results = results.filter(a => a.availability === availability);
    const total = results.length;
    results = results.slice(offset, offset + limit);
    return { agents: results, pagination: { total, limit, offset } };
  }

  search({ capability, capabilities, availability, limit = 20, offset = 0 } = {}) {
    let results = Array.from(this.agents.values());
    if (capability) results = results.filter(a => a.capabilities.includes(capability));
    if (capabilities) {
      const caps = Array.isArray(capabilities) ? capabilities : [capabilities];
      results = results.filter(a => caps.some(c => a.capabilities.includes(c)));
    }
    if (availability) results = results.filter(a => a.availability === availability);
    results.sort((a, b) => a.capabilities.length - b.capabilities.length);
    const total = results.length;
    results = results.slice(offset, offset + limit);
    return { agents: results, pagination: { total, limit, offset } };
  }
}

module.exports = { RegistryService };