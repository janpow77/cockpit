import { client, USE_MOCKS } from './client'
import { mock } from './mock'
import type { Settings } from './types'

export async function getSettings(): Promise<Settings> {
  if (USE_MOCKS) return mock.settings()
  const { data } = await client.get<Settings>('/settings')
  return data
}

export async function patchSettings(patch: { health_interval_s?: number }): Promise<Settings> {
  const { data } = await client.patch<Settings>('/settings', patch)
  return data
}
