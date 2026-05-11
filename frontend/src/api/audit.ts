import { client, USE_MOCKS } from './client'
import { mock } from './mock'
import type { AuditEntry } from './types'

export interface AuditFilter {
  actor?: string
  action?: string
  target?: string
  since?: string
  limit?: number
}

export async function listAudit(filter: AuditFilter = {}): Promise<AuditEntry[]> {
  if (USE_MOCKS) return mock.audit()
  const { data } = await client.get<AuditEntry[]>('/audit', { params: filter })
  return data
}
