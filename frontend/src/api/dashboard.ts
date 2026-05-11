import { client, USE_MOCKS } from './client'
import { mock } from './mock'
import type { DashboardStats, HealthInfo } from './types'

export async function getDashboard(): Promise<DashboardStats> {
  if (USE_MOCKS) return mock.dashboard()
  const { data } = await client.get<DashboardStats>('/dashboard')
  return data
}

export async function getHealth(): Promise<HealthInfo> {
  if (USE_MOCKS) return mock.health() as any
  const { data } = await client.get<HealthInfo>('/health')
  return data
}
