/** Core/n8n Node adapter. Service key stays server-side. No automatic side-effect retries. */
export class BrowserClient {
  constructor(baseUrl, serviceKey) {
    this.base = baseUrl.replace(/\/$/, '') + '/integration/v1';
    this.key = serviceKey;
  }
  async request(method, path, body) {
    const response = await fetch(this.base + path, {
      method,
      signal: AbortSignal.timeout(45000),
      headers: { 'X-Internal-Key': this.key, ...(body ? {'Content-Type': 'application/json'} : {}) },
      body: body ? JSON.stringify(body) : undefined
    });
    const data = await response.json();
    if (!response.ok) {
      const error = new Error(data.detail || 'Browser integration failed');
      error.status = response.status;
      throw error;
    }
    return data;
  }
  start(input) { return this.request('POST', '/sessions', input); }
  command(id, input) { return this.request('POST', `/sessions/${encodeURIComponent(id)}/commands`, input); }
  events(id, after=0) { return this.request('GET', `/events/${encodeURIComponent(id)}?after=${Math.max(0,Number(after)||0)}`); }
  humanTask(id) { return this.request('POST', '/human-tasks', {session_id:id}); }
  uploadArtifact(id, input) { return this.request('POST', `/sessions/${encodeURIComponent(id)}/artifacts`, input); }
}
