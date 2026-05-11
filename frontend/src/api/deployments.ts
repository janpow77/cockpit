import { client } from './client'
import type { Deployment, DeploymentSource, DeploymentStatus } from './types'

export async function listForApp(appId: string, limit = 50): Promise<Deployment[]> {
  const { data } = await client.get<Deployment[]>(`/apps/${appId}/deployments`, {
    params: { limit },
  })
  return data
}

export async function currentForApp(appId: string): Promise<Deployment | null> {
  const { data } = await client.get<Deployment | null>(`/apps/${appId}/deployments/current`)
  return data
}

export async function listRecent(limit = 50): Promise<Deployment[]> {
  const { data } = await client.get<Deployment[]>('/deployments/recent', {
    params: { limit },
  })
  return data
}

export interface DeploymentRecord {
  image: string
  image_digest?: string | null
  git_sha?: string | null
  source?: DeploymentSource
  actor?: string
  status?: DeploymentStatus
  notes?: string | null
  duration_s?: number | null
  ts?: string
}

export async function record(appId: string, payload: DeploymentRecord): Promise<Deployment> {
  const { data } = await client.post<Deployment>(`/apps/${appId}/deployments`, payload)
  return data
}
