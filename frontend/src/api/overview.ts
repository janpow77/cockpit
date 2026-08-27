import { client, USE_MOCKS } from './client'
import type { Overview, WallConfig, DemoStartResult } from './types'

const NOW = new Date().toISOString()

// Mock fuer VITE_USE_MOCKS=true (Layout-Arbeit ohne Backend)
function mockOverview(): Overview {
  return {
    generated_at: NOW,
    hosts: [
      { name: 'ccx23', ip: '100.99.159.80', description: 'Hetzner CCX23 — public Caddy + LLM-Router + Workshop', is_self: true, status: 'online', last_check_at: NOW,
        stats: { load1: 0.81, load5: 0.7, load15: 0.6, cpus: 4, mem_total_mb: 15990, mem_used_mb: 9210, mem_pct: 57.6, disk_total_kb: 154000000, disk_used_kb: 108000000, disk_pct: 70, uptime_s: 1036800, containers: 31, ok: true, error: null, ms: 40 },
        projects: ['regulierung', 'checklist', 'flowinvoice', 'auditworkshop', 'ai-router', 'cockpit'], project_count: 6 },
      { name: 'nuc', ip: '100.102.132.11', description: 'Workshop-Backend + audit_designer + Backfill', is_self: false, status: 'online', last_check_at: NOW,
        stats: { load1: 1.9, load5: 1.4, load15: 1.1, cpus: 12, mem_total_mb: 64000, mem_used_mb: 26000, mem_pct: 40.6, disk_total_kb: 980000000, disk_used_kb: 410000000, disk_pct: 42, uptime_s: 260000, containers: 12, ok: true, error: null, ms: 210 },
        projects: ['regulierung', 'audit_designer', 'flowinvoice'], project_count: 3 },
      { name: 'evo', ip: '100.81.4.99', description: 'Desktop Multi-GPU', is_self: false, status: 'online', last_check_at: NOW,
        stats: { load1: 0.4, load5: 0.5, load15: 0.5, cpus: 16, mem_total_mb: 128000, mem_used_mb: 30000, mem_pct: 23.4, disk_total_kb: 2000000000, disk_used_kb: 900000000, disk_pct: 45, uptime_s: 500000, containers: 3, ok: true, error: null, ms: 180 },
        projects: ['ai-router', 'ollama'], project_count: 2 },
      { name: 'macbook-air', ip: '100.70.245.26', description: 'Laptop', is_self: false, status: 'offline', last_check_at: NOW,
        stats: { load1: null, load5: null, load15: null, cpus: null, mem_total_mb: null, mem_used_mb: null, mem_pct: null, disk_total_kb: null, disk_used_kb: null, disk_pct: null, uptime_s: null, containers: null, ok: false, error: 'offline', ms: null },
        projects: [], project_count: 0 },
    ],
    projects: [
      { host: 'ccx23', name: 'regulierung', title: 'HPP · Preismonitoring-Portal', sub: 'KPAnG-Vollzug und Marktbeobachtung', containers: 5, running: 5, status: 'healthy', images: [], url: 'https://hpp.flowaudit.de', tunnel: true, registered: true, app_id: 'a1', app_status: 'healthy', last_check_at: NOW, deploy: { ts: NOW, git_sha: '19ed003', image: 'regulierung-backend', status: 'ok' } },
      { host: 'ccx23', name: 'checklist', title: 'Checklisten-Designer', sub: 'EFRE-Prüfung · audit_designer', containers: 9, running: 9, status: 'healthy', images: [], url: 'https://checklist.flowaudit.de', tunnel: true, registered: true, app_id: 'a2', app_status: 'healthy', last_check_at: NOW, deploy: null },
      { host: 'ccx23', name: 'flowinvoice', title: 'flowinvoice', sub: 'Belegprüfung mit Erkennung', containers: 8, running: 8, status: 'healthy', images: [], url: null, intern: [{ url: 'http://100.99.159.80:8020', service: 'frontend', port: 8020 }], tunnel: false, registered: false, app_id: null, app_status: null, last_check_at: null, deploy: null },
      { host: 'ccx23', name: 'auditworkshop', title: 'Workshop', sub: 'Seminar-Plattform', containers: 3, running: 3, status: 'healthy', images: [], url: 'https://workshop.flowaudit.de', tunnel: false, registered: true, app_id: 'a3', app_status: 'degraded', last_check_at: NOW, deploy: null },
      { host: 'ccx23', name: 'ai-router', title: 'ai-router', sub: 'LLM-Gateway · Spokes EVO/NUC', containers: 1, running: 1, status: 'healthy', images: [], url: null, tunnel: false, registered: true, app_id: 'a4', app_status: 'healthy', last_check_at: NOW, deploy: null },
      { host: 'ccx23', name: 'cockpit', title: 'cockpit', sub: 'Diese Wand', containers: 1, running: 1, status: 'healthy', images: [], url: null, tunnel: false, registered: false, app_id: null, app_status: null, last_check_at: null, deploy: null },
      { host: 'nuc', name: 'regulierung', title: 'HPP · Preismonitoring-Portal', sub: 'Entwicklung', containers: 5, running: 5, status: 'healthy', images: [], url: null, tunnel: false, registered: true, app_id: 'a5', app_status: 'healthy', last_check_at: NOW, deploy: null },
      { host: 'nuc', name: 'audit_designer', title: 'audit_designer', sub: '', containers: 6, running: 5, status: 'degraded', images: [], url: null, tunnel: false, registered: true, app_id: 'a6', app_status: 'degraded', last_check_at: NOW, deploy: null },
      { host: 'evo', name: 'ai-router', title: 'ai-router', sub: 'Spoke EVO', containers: 2, running: 2, status: 'healthy', images: [], url: null, tunnel: false, registered: false, app_id: null, app_status: null, last_check_at: null, deploy: null },
    ],
    hero: { project: 'hpp', title: 'HPP · Preismonitoring-Portal', sub: 'Landeskartellbehörde Hessen · KPAnG-Vollzug', url: 'https://hpp.flowaudit.de', demo_path: '/kraftstoff/vollzug/demo', probe: 'hpp',
      project_state: null, kpis: [{ label: 'Meldungen 24 h', value: 34445 }, { label: 'Tankstellen', value: 2766 }, { label: 'Verdachtsfälle 24 h', value: 238 }, { label: 'Verfahren offen', value: 5 }], probe_note: null, demo_ready: true },
    probes: [
      { id: 'hpp', label: 'HPP', ok: true, kpis: [{ label: 'Meldungen 24 h', value: 34445 }], note: null },
      { id: 'kira', label: 'Kira-RAG', ok: true, kpis: [{ label: 'Einträge', value: 1284 }], note: null },
    ],
    backups: [
      { name: 'checklist', file: 'checklist-20260827-032000.dump.age', mtime: NOW, size_bytes: 2100000000, age_h: 6.2, status: 'ok' },
      { name: 'hpp', file: 'hpp-20260827-031000.dump.age', mtime: NOW, size_bytes: 676000000, age_h: 6.4, status: 'ok' },
    ],
    ai_router: { ok: true, url: 'http://100.99.159.80:7842', model_count: 20, models: ['qwen3.8-heretic:27b', 'qwen3.5:35b-fast', 'qwen3:14b'], freigegeben: ['Qwen 3.8 · 27B', 'Qwen 3.5 · 35B (schnell)'] },
    github: { enabled: true, error: null,
      repos: [
        { full_name: 'janpow77/regulierung', name: 'regulierung', owner: 'janpow77', description: 'HPP', private: true, language: 'Python', pushed_at: NOW, default_branch: 'main', open_issues: 0, stars: 0, html_url: '#' },
        { full_name: 'janpow77/flow-agent', name: 'flow-agent', owner: 'janpow77', description: 'Agent', private: true, language: 'TypeScript', pushed_at: NOW, default_branch: 'main', open_issues: 2, stars: 0, html_url: '#' },
        { full_name: 'janpow77/cockpit', name: 'cockpit', owner: 'janpow77', description: 'Diese Wand', private: true, language: 'Python', pushed_at: NOW, default_branch: 'main', open_issues: 0, stars: 0, html_url: '#' },
      ],
      commits: [
        { repo: 'janpow77/regulierung', sha: '19ed003', message: 'docs(vorfuehrung): Folien zu IT-Bedarf, Datenschutz/AI Act und BSI-Grundschutz ergänzt', author: 'Jan', date: NOW, html_url: '#' },
        { repo: 'janpow77/regulierung', sha: '1f19f9f', message: 'fix(kpang): Plausiprotokoll-Zeile nach Feststellung erhalten', author: 'Jan', date: NOW, html_url: '#' },
      ] },
    events: [
      { ts: NOW, kind: 'commit', text: 'regulierung 19ed003 · docs(vorfuehrung): Folien ergänzt' },
      { ts: NOW, kind: 'deploy', text: 'Deploy regulierung-backend 19ed003 · ok' },
      { ts: NOW, kind: 'audit', text: 'app.restart checklist' },
    ],
    links: {},
    alerts: [
      { level: 'warn', text: 'Workshop auf ccx23: 2/3 Container laufen', host: 'ccx23', hint: null, url: 'https://workshop.flowaudit.de' },
      { level: 'info', text: 'Pause offen in cockpit (nuc)', host: 'nuc', hint: 'ChatView bauen, dann Deploy', url: null },
    ],
    dienste: [
      { url: 'https://hpp.flowaudit.de', host: 'hpp.flowaudit.de', ok: true, status_code: 200, ms: 142, note: null, tls_bis: NOW, tls_tage: 61, tls_aussteller: "Let's Encrypt", tls_fehler: null, requests_24h: 1840, verlauf: [12, 30, 8, 4, 2, 1, 3, 9, 40, 120, 160, 150, 130, 140, 160, 170, 150, 120, 90, 70, 60, 50, 40, 20], fehler_5xx: 0 },
      { url: 'https://checklist.flowaudit.de', host: 'checklist.flowaudit.de', ok: true, status_code: 200, ms: 98, note: null, tls_bis: NOW, tls_tage: 61, tls_aussteller: "Let's Encrypt", tls_fehler: null, requests_24h: 620, verlauf: [2, 3, 1, 0, 0, 0, 1, 5, 30, 60, 70, 65, 50, 55, 60, 70, 50, 40, 20, 15, 10, 8, 5, 2], fehler_5xx: 0 },
      { url: 'https://zvg.flowaudit.de', host: 'zvg.flowaudit.de', ok: false, status_code: null, ms: 8000, note: 'ConnectTimeout', tls_bis: null, tls_tage: null, tls_aussteller: null, tls_fehler: 'timed out', requests_24h: null, verlauf: [], fehler_5xx: null },
    ],
    werkstatt: [
      { host: 'nuc', ok: true, error: null, dirty: 2, pausen: 1, ms: 3200, collected_at: NOW, repo_count: 3, repos: [
        { name: 'cockpit', branch: 'main', dirty: 14, ahead: 0, last_commit: NOW, age_h: 5.5, message: 'feat(wand): Landschaft und Leitstand', pause: NOW, next_step: 'ChatView bauen, dann Deploy' },
        { name: 'regulierung', branch: 'main', dirty: 1, ahead: 0, last_commit: NOW, age_h: 20, message: 'docs(vorfuehrung): Folien ergänzt', pause: null, next_step: null },
        { name: 'audit_designer', branch: 'main', dirty: 0, ahead: null, last_commit: NOW, age_h: 90, message: 'fix(memory): Ratelimit', pause: null, next_step: null },
      ] },
      { host: 'ccx23', ok: true, error: null, dirty: 0, pausen: 0, ms: 900, collected_at: NOW, repo_count: 1, repos: [
        { name: 'regulierung', branch: 'main', dirty: 0, ahead: 0, last_commit: NOW, age_h: 21, message: 'docs(vorfuehrung): Folien ergänzt', pause: null, next_step: null },
      ] },
    ],
    kira: { ok: true, total: 1284, note: null, host: 'nuc', entries: [
      { id: '1', category: 'architecture', project: 'regulierung', text: 'Demo-Modus: in-process httpx.ASGITransport fährt die eigene API, Vorgang.ist_demo markiert Demo-Daten', tags: ['demo', 'kpang'], created_at: NOW },
      { id: '2', category: 'solution', project: 'regulierung', text: 'Append-only-Trigger beim Demo-Löschen in der Transaktion pausieren (ADR-004)', tags: ['trigger'], created_at: NOW },
    ] },
  }
}

export async function getOverview(): Promise<Overview> {
  if (USE_MOCKS) return mockOverview()
  const { data } = await client.get<Overview>('/overview', { timeout: 90_000 })
  return data
}

export async function getWallConfig(): Promise<WallConfig> {
  const { data } = await client.get<WallConfig>('/overview/config')
  return data
}

export async function patchWallConfig(patch: Partial<WallConfig>): Promise<WallConfig> {
  const { data } = await client.patch<WallConfig>('/overview/config', patch)
  return data
}

export async function startDemo(neu = false): Promise<DemoStartResult> {
  if (USE_MOCKS) return { ok: true, uebersprungen: !neu, faelle: [{ aktenzeichen: 'DEMO-2026/005', schritte: 1, fehler: null }], url: 'https://hpp.flowaudit.de/kraftstoff/vollzug' }
  const { data } = await client.post<DemoStartResult>('/overview/demo', { neu }, { timeout: 660_000 })
  return data
}
