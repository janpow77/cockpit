// Geteilte Domain-Typen — abgeleitet aus api-contract.md

export interface Host {
  id: string
  name: string
  tailscale_ip: string
  description: string
  ssh_user: string | null
  ssh_key_path: string | null
  is_self: boolean
  enabled: boolean
  last_check_at: string | null
  last_status: string
  last_error: string | null
  created_at: string
  updated_at: string
}

export interface ContainerInfo {
  name: string
  image: string
  state: string
  status: string
  ports: string
}

export interface App {
  id: string
  host_id: string
  host_name: string
  name: string
  description: string
  container_filter: string
  compose_path: string | null
  healthcheck_url: string | null
  tags: string[]
  enabled: boolean
  last_check_at: string | null
  last_status: string
  container_count: number
  healthy_count: number
  created_at: string
  updated_at: string
}

export interface AppDetail extends App {
  containers: ContainerInfo[]
  health_http: { ok: boolean; status?: number; error?: string } | null
}

export interface Repo {
  id: string
  owner: string
  name: string
  description: string
  default_branch: string
  enabled: boolean
  last_sync_at: string | null
  created_at: string
  updated_at: string
}

export interface Backup {
  id: string
  name: string
  host_id: string
  host_name: string
  backup_type: string
  command: string
  target_path: string
  schedule_cron: string | null
  enabled: boolean
  last_run_at: string | null
  last_run_status: string
  last_size_bytes: number | null
  created_at: string
  updated_at: string
}

export interface BackupRunResult {
  ok: boolean
  duration_ms: number
  bytes: number | null
  log: string
  error: string | null
}

export interface Secret {
  id: string
  key: string
  app_tag: string | null
  host_tag: string | null
  comment: string
  last_used_at: string | null
  last_used_purpose: string | null
  reveal_count: number
  created_at: string
  updated_at: string
}

export interface SecretReveal {
  id: string
  key: string
  value: string
  revealed_at: string
  purpose: string
}

export interface AuditEntry {
  id: string
  ts: string
  actor: string
  action: string
  target: string | null
  before: Record<string, unknown> | null
  after: Record<string, unknown> | null
  ip: string | null
  notes: string | null
}

export interface DashboardStats {
  apps_total: number
  apps_healthy: number
  apps_down: number
  apps_unknown: number
  hosts_total: number
  hosts_online: number
  last_backup_at: string | null
  last_backup_status: string | null
  backups_total: number
  secrets_total: number
  repos_total: number
  recent_audit: AuditEntry[]
}

export interface Settings {
  cockpit_version: string
  uptime_seconds: number
  self_host_name: string
  data_dir: string
  config_path: string
  vault_enabled: boolean
  github_enabled: boolean
  admin_password_is_default: boolean
  health_interval_s: number
}

export interface HealthInfo {
  status: 'ok' | 'degraded' | 'down'
  version: string
  started_at: string
  uptime_s: number
}
