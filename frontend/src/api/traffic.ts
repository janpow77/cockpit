import { client } from './client'
import type {
  ServerAppMapEntry,
  TrafficBucketSize,
  TrafficSeries,
  TrafficSource,
} from './types'

export async function listSources(): Promise<TrafficSource[]> {
  const { data } = await client.get<TrafficSource[]>('/traffic/sources')
  return data
}

export interface TrafficSourceCreate {
  host_id: string
  log_path: string
  log_format?: string
  server_app_map?: ServerAppMapEntry[]
  enabled?: boolean
}

export async function createSource(payload: TrafficSourceCreate): Promise<TrafficSource> {
  const { data } = await client.post<TrafficSource>('/traffic/sources', payload)
  return data
}

export async function updateSource(
  id: string,
  patch: Partial<TrafficSourceCreate>,
): Promise<TrafficSource> {
  const { data } = await client.patch<TrafficSource>(`/traffic/sources/${id}`, patch)
  return data
}

export async function deleteSource(id: string): Promise<void> {
  await client.delete(`/traffic/sources/${id}`)
}

export interface CollectResult {
  sources: number
  ok: number
  failed: number
  lines: number
}

export async function collectNow(): Promise<CollectResult> {
  const { data } = await client.post<CollectResult>('/traffic/collect')
  return data
}

export interface SeriesQuery {
  app_id?: string
  host_id?: string
  server_name?: string
  bucket?: TrafficBucketSize
  window?: string // z.B. '6h', '30m', '7d'
}

export async function getSeries(query: SeriesQuery = {}): Promise<TrafficSeries> {
  const { data } = await client.get<TrafficSeries>('/traffic/series', {
    params: {
      app_id: query.app_id,
      host_id: query.host_id,
      server_name: query.server_name,
      bucket: query.bucket ?? '5m',
      window: query.window ?? '6h',
    },
  })
  return data
}

export async function purgeOlderThan(days = 90): Promise<{ deleted: number }> {
  const { data } = await client.post('/traffic/purge', null, { params: { days } })
  return data
}
