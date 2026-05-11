import { client, USE_MOCKS } from './client'
import { mock } from './mock'
import type { App, AppDetail } from './types'

export async function listApps(): Promise<App[]> {
  if (USE_MOCKS) return mock.apps()
  const { data } = await client.get<App[]>('/apps')
  return data
}

export async function getApp(id: string): Promise<AppDetail> {
  if (USE_MOCKS) return mock.appDetail(id)
  const { data } = await client.get<AppDetail>(`/apps/${id}`)
  return data
}

export interface AppCreate {
  host_id: string
  name: string
  description?: string
  container_filter?: string
  compose_path?: string | null
  healthcheck_url?: string | null
  tags?: string[]
  enabled?: boolean
}

export async function createApp(payload: AppCreate): Promise<App> {
  const { data } = await client.post<App>('/apps', payload)
  return data
}

export async function updateApp(id: string, patch: Partial<AppCreate>): Promise<App> {
  const { data } = await client.patch<App>(`/apps/${id}`, patch)
  return data
}

export async function deleteApp(id: string): Promise<void> {
  await client.delete(`/apps/${id}`)
}

export async function appHealthCheck(id: string): Promise<App> {
  const { data } = await client.post<App>(`/apps/${id}/health-check`)
  return data
}

export async function restartApp(id: string): Promise<{ ok: boolean; log: string; error: string | null }> {
  const { data } = await client.post(`/apps/${id}/restart`)
  return data
}

export async function appLogs(id: string, tail = 200): Promise<{ logs: string }> {
  if (USE_MOCKS) return mock.appLogs(id) as any
  const { data } = await client.get(`/apps/${id}/logs`, { params: { tail } })
  return data
}
