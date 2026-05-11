import { client, USE_MOCKS } from './client'
import { mock } from './mock'
import type { Secret, SecretReveal } from './types'

export async function listSecrets(): Promise<Secret[]> {
  if (USE_MOCKS) return mock.secrets()
  const { data } = await client.get<Secret[]>('/secrets')
  return data
}

export interface SecretCreate {
  key: string
  value: string
  app_tag?: string | null
  host_tag?: string | null
  comment?: string
}

export async function createSecret(payload: SecretCreate): Promise<Secret> {
  const { data } = await client.post<Secret>('/secrets', payload)
  return data
}

export async function updateSecret(id: string, patch: Partial<SecretCreate>): Promise<Secret> {
  const { data } = await client.patch<Secret>(`/secrets/${id}`, patch)
  return data
}

export async function deleteSecret(id: string): Promise<void> {
  await client.delete(`/secrets/${id}`)
}

export async function revealSecret(id: string, purpose: string): Promise<SecretReveal> {
  const { data } = await client.post<SecretReveal>(`/secrets/${id}/reveal`, { purpose })
  return data
}
