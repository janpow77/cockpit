import { client, USE_MOCKS } from './client'
import { mock } from './mock'
import type { Repo } from './types'

export async function listRepos(): Promise<Repo[]> {
  if (USE_MOCKS) return mock.repos()
  const { data } = await client.get<Repo[]>('/github/repos')
  return data
}

export interface RepoCreate {
  owner: string
  name: string
  description?: string
  default_branch?: string
}

export async function addRepo(payload: RepoCreate): Promise<Repo> {
  const { data } = await client.post<Repo>('/github/repos', payload)
  return data
}

export async function updateRepo(id: string, patch: { description?: string; enabled?: boolean }): Promise<Repo> {
  const { data } = await client.patch<Repo>(`/github/repos/${id}`, patch)
  return data
}

export async function deleteRepo(id: string): Promise<void> {
  await client.delete(`/github/repos/${id}`)
}

export async function repoBranches(owner: string, name: string): Promise<{ name: string; sha: string }[]> {
  const { data } = await client.get(`/github/repos/${owner}/${name}/branches`)
  return data
}

export async function repoPRs(owner: string, name: string, state = 'open'): Promise<any[]> {
  const { data } = await client.get(`/github/repos/${owner}/${name}/prs`, { params: { state } })
  return data
}

export async function repoRuns(owner: string, name: string, limit = 10): Promise<any[]> {
  const { data } = await client.get(`/github/repos/${owner}/${name}/runs`, { params: { limit } })
  return data
}

export async function repoMeta(owner: string, name: string): Promise<any> {
  const { data } = await client.get(`/github/repos/${owner}/${name}/meta`)
  return data
}
