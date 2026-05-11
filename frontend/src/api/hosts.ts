import { client, USE_MOCKS } from './client'
import { mock } from './mock'
import type { Host } from './types'

export async function listHosts(): Promise<Host[]> {
  if (USE_MOCKS) return mock.hosts()
  const { data } = await client.get<Host[]>('/hosts')
  return data
}

export async function getHost(id: string): Promise<Host> {
  if (USE_MOCKS) {
    const h = (await mock.hosts()).find(x => x.id === id)
    if (!h) throw new Error('not found')
    return h
  }
  const { data } = await client.get<Host>(`/hosts/${id}`)
  return data
}

export interface HostCreate {
  name: string
  tailscale_ip: string
  description?: string
  ssh_user?: string | null
  ssh_key_path?: string | null
  is_self?: boolean
  enabled?: boolean
}

export async function createHost(payload: HostCreate): Promise<Host> {
  const { data } = await client.post<Host>('/hosts', payload)
  return data
}

export async function updateHost(id: string, patch: Partial<HostCreate>): Promise<Host> {
  const { data } = await client.patch<Host>(`/hosts/${id}`, patch)
  return data
}

export async function deleteHost(id: string): Promise<void> {
  await client.delete(`/hosts/${id}`)
}

export async function checkHost(id: string): Promise<{ host: Host; check: any }> {
  const { data } = await client.get(`/hosts/${id}/health`)
  return data
}

export async function tailscaleStatus(): Promise<any> {
  const { data } = await client.get('/hosts/tailscale-status')
  return data
}
