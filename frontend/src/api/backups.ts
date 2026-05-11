import { client, USE_MOCKS } from './client'
import { mock } from './mock'
import type { Backup, BackupRunResult } from './types'

export async function listBackups(): Promise<Backup[]> {
  if (USE_MOCKS) return mock.backups()
  const { data } = await client.get<Backup[]>('/backups')
  return data
}

export interface BackupCreate {
  name: string
  host_id: string
  backup_type: 'postgres' | 'rsync' | 'docker_volume' | 'shell'
  command: string
  target_path: string
  schedule_cron?: string | null
  enabled?: boolean
}

export async function createBackup(payload: BackupCreate): Promise<Backup> {
  const { data } = await client.post<Backup>('/backups', payload)
  return data
}

export async function updateBackup(id: string, patch: Partial<BackupCreate>): Promise<Backup> {
  const { data } = await client.patch<Backup>(`/backups/${id}`, patch)
  return data
}

export async function deleteBackup(id: string): Promise<void> {
  await client.delete(`/backups/${id}`)
}

export async function runBackup(id: string): Promise<BackupRunResult> {
  const { data } = await client.post<BackupRunResult>(`/backups/${id}/run`)
  return data
}

export async function restoreTest(id: string): Promise<any> {
  const { data } = await client.post(`/backups/${id}/restore-test`)
  return data
}
