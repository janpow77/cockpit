import { client, USE_MOCKS } from './client'
import type { McpServerState } from './types'

export async function listMcpServers(): Promise<{ servers: McpServerState[] }> {
  if (USE_MOCKS) {
    return { servers: [{
      id: 'flowaudit', name: 'flowaudit – Humanizer, Standards, Skills', transport: 'http', url: 'https://mcp.flowaudit.de/mcp', command: null,
      description: 'Schreibstil, Terminologie, Standards.', secret_key: 'mcp_flowaudit_token', secret_ok: true, header: 'Authorization',
      snippet: 'claude mcp add --transport http flowaudit https://mcp.flowaudit.de/mcp --header "Authorization: Bearer <SECRET>"',
      health: null, inspect: { ok: true, error: null, server: { name: 'flowaudit', version: '1.0' }, tools: [{ name: 'skills_list', description: 'Skill-Katalog' }, { name: 'humanizer_check', description: 'Stilprüfung' }], skills: [{ name: 'deutsche-formulierung', description: 'Umlaute und Fachbegriffe' }] },
    }] }
  }
  const { data } = await client.get<{ servers: McpServerState[] }>('/mcp/servers', { timeout: 60_000 })
  return data
}
