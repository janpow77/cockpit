// Mock-Daten fuer VITE_USE_MOCKS=true. Hardcoded Beispiel-Daten fuer Demo/Tests
// ohne Backend.

import type {
  App, AuditEntry, Backup, DashboardStats, Host, Repo, Secret, Settings, ContainerInfo,
} from './types'

const NOW = new Date().toISOString()

export const mockHosts: Host[] = [
  {
    id: 'h_self', name: 'ccx23', tailscale_ip: '100.99.159.80', description: 'Hetzner CCX23 Cloud',
    ssh_user: null, ssh_key_path: null, is_self: true, enabled: true,
    last_check_at: NOW, last_status: 'online', last_error: null, created_at: NOW, updated_at: NOW,
  },
  {
    id: 'h_nuc', name: 'nuc', tailscale_ip: '100.102.132.11', description: 'NUC15 — Workshop + audit_designer',
    ssh_user: 'janpow', ssh_key_path: '/root/.ssh/cockpit_id_ed25519', is_self: false, enabled: true,
    last_check_at: NOW, last_status: 'online', last_error: null, created_at: NOW, updated_at: NOW,
  },
  {
    id: 'h_evo', name: 'evo', tailscale_ip: '100.81.4.99', description: 'Desktop Multi-GPU',
    ssh_user: 'janpow', ssh_key_path: '/root/.ssh/cockpit_id_ed25519', is_self: false, enabled: true,
    last_check_at: NOW, last_status: 'offline', last_error: 'connect timeout', created_at: NOW, updated_at: NOW,
  },
]

export const mockApps: App[] = [
  { id: 'a1', host_id: 'h_self', host_name: 'ccx23', name: 'auditworkshop', description: '',
    container_filter: 'name=auditworkshop-', compose_path: '/opt/auditworkshop/compose.yaml',
    healthcheck_url: 'http://127.0.0.1:3004/', tags: ['workshop', 'public'], enabled: true,
    last_check_at: NOW, last_status: 'healthy', container_count: 2, healthy_count: 2,
    created_at: NOW, updated_at: NOW },
  { id: 'a2', host_id: 'h_self', host_name: 'ccx23', name: 'llm-router', description: '',
    container_filter: 'name=llm-router', compose_path: '/opt/llm-router/compose.yaml',
    healthcheck_url: 'http://100.99.159.80:7842/health', tags: ['service', 'llm'], enabled: true,
    last_check_at: NOW, last_status: 'healthy', container_count: 1, healthy_count: 1,
    created_at: NOW, updated_at: NOW },
  { id: 'a3', host_id: 'h_nuc', host_name: 'nuc', name: 'audit_designer', description: '',
    container_filter: 'name=audit_designer', compose_path: null, healthcheck_url: null,
    tags: ['main'], enabled: true,
    last_check_at: NOW, last_status: 'healthy', container_count: 8, healthy_count: 8,
    created_at: NOW, updated_at: NOW },
  { id: 'a4', host_id: 'h_evo', host_name: 'evo', name: 'gpu-llm-manager', description: '',
    container_filter: 'name=gpu-', compose_path: null, healthcheck_url: null,
    tags: ['gpu'], enabled: true,
    last_check_at: NOW, last_status: 'unknown', container_count: 0, healthy_count: 0,
    created_at: NOW, updated_at: NOW },
]

export const mockContainers: ContainerInfo[] = [
  { name: 'auditworkshop-frontend', image: 'auditworkshop-frontend:latest', state: 'running',
    status: 'Up 2 hours (healthy)', ports: '127.0.0.1:3004->80/tcp' },
  { name: 'auditworkshop-backend', image: 'auditworkshop-backend:latest', state: 'running',
    status: 'Up 2 hours (healthy)', ports: '' },
]

export const mockRepos: Repo[] = [
  { id: 'r1', owner: 'janriener', name: 'cockpit', description: 'This very tool',
    default_branch: 'main', enabled: true, last_sync_at: NOW, created_at: NOW, updated_at: NOW },
  { id: 'r2', owner: 'janriener', name: 'audit_designer', description: 'Hauptprojekt',
    default_branch: 'main', enabled: true, last_sync_at: NOW, created_at: NOW, updated_at: NOW },
]

export const mockBackups: Backup[] = [
  { id: 'b1', name: 'auditworkshop-db-daily', host_id: 'h_self', host_name: 'ccx23',
    backup_type: 'postgres', command: 'pg_dumpall | gzip > /backups/wsdb-$(date +%F).sql.gz',
    target_path: '/backups/wsdb.sql.gz', schedule_cron: '0 2 * * *', enabled: true,
    last_run_at: NOW, last_run_status: 'ok', last_size_bytes: 12_456_789,
    created_at: NOW, updated_at: NOW },
]

export const mockSecrets: Secret[] = [
  { id: 's1', key: 'GITHUB_TOKEN', app_tag: 'cockpit', host_tag: null, comment: 'Read-only PAT',
    last_used_at: NOW, last_used_purpose: 'github sync', reveal_count: 3,
    created_at: NOW, updated_at: NOW },
  { id: 's2', key: 'OPENAI_API_KEY', app_tag: 'audit_designer', host_tag: null, comment: '',
    last_used_at: null, last_used_purpose: null, reveal_count: 0, created_at: NOW, updated_at: NOW },
]

export const mockAudit: AuditEntry[] = [
  { id: 'a1', ts: NOW, actor: 'admin', action: 'host.create', target: 'h_self',
    before: null, after: { name: 'ccx23' }, ip: '127.0.0.1', notes: null },
  { id: 'a2', ts: NOW, actor: 'admin', action: 'app.restart', target: 'a1',
    before: null, after: { name: 'auditworkshop', ok: true }, ip: '127.0.0.1', notes: null },
]

export const mockDashboard: DashboardStats = {
  apps_total: mockApps.length,
  apps_healthy: mockApps.filter(a => a.last_status === 'healthy').length,
  apps_down: mockApps.filter(a => a.last_status === 'down').length,
  apps_unknown: mockApps.filter(a => a.last_status === 'unknown').length,
  hosts_total: mockHosts.length,
  hosts_online: mockHosts.filter(h => h.last_status === 'online').length,
  last_backup_at: NOW,
  last_backup_status: 'ok',
  backups_total: mockBackups.length,
  secrets_total: mockSecrets.length,
  repos_total: mockRepos.length,
  recent_audit: mockAudit,
}

export const mockSettings: Settings = {
  cockpit_version: '0.1.0',
  uptime_seconds: 3600,
  self_host_name: 'ccx23',
  data_dir: '/data',
  config_path: '/etc/cockpit/config.yaml',
  vault_enabled: true,
  github_enabled: false,
  admin_password_is_default: true,
  health_interval_s: 60,
}

export const mock = {
  login: async (password: string) => {
    if (password !== 'admin' && password !== 'cockpit-admin') throw new Error('Invalid password')
    return { token: 'mock-token-xyz', expires_at: new Date(Date.now() + 86400_000).toISOString() }
  },
  logout: async () => { /* noop */ },
  me: async () => ({ logged_in: true, expires_at: new Date(Date.now() + 86400_000).toISOString() }),
  health: async () => ({ status: 'ok' as const, version: '0.1.0-mock', started_at: NOW, uptime_s: 3600 }),
  dashboard: async () => mockDashboard,
  hosts: async () => mockHosts,
  apps: async () => mockApps,
  appDetail: async (id: string) => {
    const a = mockApps.find(x => x.id === id)
    if (!a) throw new Error('not found')
    return { ...a, containers: mockContainers, health_http: { ok: true, status: 200 } }
  },
  appLogs: async (id: string) => ({ app_id: id, tail: 200, logs: '[mock] log line 1\n[mock] log line 2\n[mock] no real backend connected.' }),
  repos: async () => mockRepos,
  backups: async () => mockBackups,
  secrets: async () => mockSecrets,
  audit: async () => mockAudit,
  settings: async () => mockSettings,
}
