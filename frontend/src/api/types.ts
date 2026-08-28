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

// ---------- Traffic ----------

export type TrafficBucketSize = '1m' | '5m' | '1h' | '1d'

export interface ServerAppMapEntry {
  server_name: string
  app_name: string
}

export interface TrafficSource {
  id: string
  host_id: string
  host_name: string
  log_path: string
  log_format: string
  server_app_map: ServerAppMapEntry[]
  last_collect_at: string | null
  last_status: string
  last_error: string | null
  enabled: boolean
  created_at: string
  updated_at: string
}

export interface TrafficPoint {
  bucket_ts: string
  requests: number
  status_2xx: number
  status_3xx: number
  status_4xx: number
  status_5xx: number
  bytes_out: number
  latency_p50_ms: number | null
  latency_p95_ms: number | null
  latency_max_ms: number | null
}

export interface TrafficSeries {
  bucket_size: TrafficBucketSize
  app_id: string | null
  host_id: string | null
  from_ts: string
  to_ts: string
  total_requests: number
  error_rate: number
  points: TrafficPoint[]
}

// ---------- Deployments ----------

export type DeploymentSource = 'lifecycle' | 'gh-action' | 'manual' | 'unknown'
export type DeploymentStatus = 'ok' | 'failed' | 'started' | 'rolled_back'

export interface Deployment {
  id: string
  app_id: string
  app_name: string
  ts: string
  image: string
  image_digest: string | null
  git_sha: string | null
  source: DeploymentSource | string
  actor: string
  status: DeploymentStatus | string
  notes: string | null
  duration_s: number | null
  created_at: string
}

// ---------------------------------------------------------------------------
// Wand (Overview) und KI-Konsole
// ---------------------------------------------------------------------------

export interface HostStats {
  load1: number | null
  load5: number | null
  load15: number | null
  cpus: number | null
  mem_total_mb: number | null
  mem_used_mb: number | null
  mem_pct: number | null
  disk_total_kb: number | null
  disk_used_kb: number | null
  disk_pct: number | null
  uptime_s: number | null
  containers: number | null
  gpus?: { util_pct: number; mem_used_mb: number | null; mem_total_mb: number | null }[]
  tmux?: TmuxSitzung[]
  ok: boolean
  error: string | null
  ms: number | null
}

export interface WallHost {
  name: string
  ip: string
  description: string
  is_self: boolean
  status: string
  last_check_at: string | null
  stats: HostStats
  tmux?: TmuxSitzung[]
  projects: string[]
  project_count: number
}

export interface WallProject {
  host: string
  name: string
  title: string
  sub: string
  containers: number
  running: number
  status: string
  images: string[]
  names?: string[]
  url: string | null
  intern?: { url: string; service: string; port: number }[]
  tunnel: boolean
  registered: boolean
  app_id: string | null
  app_status: string | null
  last_check_at: string | null
  deploy: { ts: string; git_sha: string; image: string; status: string } | null
}

export interface Kpi { label: string; value: number | string }

export interface WallProbe { id: string; label: string; ok: boolean; kpis: Kpi[]; note: string | null }

export interface WallBackup { name: string; file: string; mtime: string; size_bytes: number; age_h: number; status: 'ok' | 'warn' | 'krit' }

export interface GithubRepo {
  full_name: string; name: string; owner: string; description: string; private: boolean
  language: string; pushed_at: string | null; default_branch: string; open_issues: number; stars: number; html_url: string
}

export interface GithubCommit { repo: string; sha: string; message: string; author: string; date: string | null; html_url: string }

export interface WallEvent { ts: string; kind: 'audit' | 'deploy' | 'commit'; text: string }

export interface FlowAgentHost {
  host: string; hostname: string; status: 'healthy' | 'degraded' | 'offline' | 'unhealthy' | 'unknown' | string
  alter_s: number | null; projekte: number; container: number; gpu: number; tmux: string | null; werkzeuge_fehlen: string[]
}
export interface FlowAgentBefund { host: string; label: string; status: string; detail: string }
export interface FlowAgentStand {
  ok: boolean; note: string | null; url: string | null; version: string | null; stand: string | null
  hosts: FlowAgentHost[]
  frische: { status: string; healthy: number; degraded: number; unhealthy: number; befunde: FlowAgentBefund[] }
  meldungen: { hosts_offline: string[]; hosts_degraded: string[]; pending_actions: number; failed_actions_recent: number }
}

export interface Overview {
  generated_at: string
  hosts: WallHost[]
  projects: WallProject[]
  hero: {
    project: string; title: string; sub: string; url: string; demo_path: string; probe: string
    project_state: WallProject | null; kpis: Kpi[]; probe_note: string | null; demo_ready: boolean
  }
  probes: WallProbe[]
  backups: WallBackup[]
  ai_router: { ok: boolean; url: string; model_count: number; models: string[]; freigegeben: string[] }
  github: { enabled: boolean; repos: GithubRepo[]; commits: GithubCommit[]; error: string | null }
  events: WallEvent[]
  links: Record<string, string>
  alerts: WallAlert[]
  dienste: WallDienst[]
  werkstatt: WerkstattHost[]
  kira: KiraStand
  flow_agent: FlowAgentStand
  ki_nutzung?: KiNutzung
}

export interface KiLimit { label: string; prozent: number; reset: string | null }
export interface KiDienst {
  verfuegbar: boolean; hinweis?: string | null; plan?: string | null; stufe?: string | null; stand?: string | null
  limits?: Record<string, KiLimit>
  heute?: { out: number; kontext: number; sitzungen?: number; modelle?: Record<string, { out: number; kontext: number }> }
  tage?: { tag: string; out: number; kontext: number; sitzungen?: number }[]
}
export interface KiNutzung { ok: boolean; hinweis?: string | null; host?: string; claude: KiDienst; codex: KiDienst; gemini: KiDienst }
export interface TmuxSitzung { name: string; attached: boolean; created: number | null; windows: { name: string; index?: string; active: boolean; cmd: string }[] }
export interface VerlaufAntwort { hours: number; series: Record<string, [string, number][]> }
export interface WallAlert { level: 'krit' | 'warn' | 'info'; text: string; host: string | null; hint: string | null; url: string | null }
export interface WallDienst {
  url: string; host: string; ok: boolean; status_code: number | null; ms: number | null; note: string | null
  tls_bis: string | null; tls_tage: number | null; tls_aussteller: string | null; tls_fehler: string | null
  requests_24h: number | null; verlauf: number[]; fehler_5xx: number | null
}
export interface WerkstattRepo {
  name: string; branch: string; dirty: number; ahead: number | null; last_commit: string | null; age_h: number | null
  message: string; pause: string | null; next_step: string | null; aktiv?: boolean
}
export interface WerkstattHost { host: string; ok: boolean; error: string | null; repos: WerkstattRepo[]; repo_count?: number; aktiv?: number; dirty: number; pausen: number; ms: number | null; collected_at: string | null }
export interface KiraEintrag { id: string | null; category: string | null; project: string | null; text: string; tags: string[]; created_at: string | null }
export interface KiraStand { ok: boolean; total: number | null; entries: KiraEintrag[]; note: string | null; host?: string | null }

export interface WallConfig {
  hosts: string[]
  hide: string[]
  links: Record<string, string>
  labels: Record<string, { title: string; sub: string }>
  hero: Record<string, string>
  probes: Record<string, unknown>[]
  demo: Record<string, string>
  backup_dir: string
  chat_models: { tag: string; label: string }[]
  chat_system: string
  chat_num_ctx?: number
  chat_think?: boolean
  mcp_servers: Record<string, unknown>[]
  work_dirs: Record<string, string>
  kira: Record<string, string>
  agent_bins: Record<string, string>
  vorschlaege: Record<string, unknown>
  auftrag_vorlagen: Record<string, unknown>[]
  auftrag_parallel: number
  codex_sandbox: 'danger-full-access' | 'workspace-write'
  flow_agent: Record<string, unknown>
  prod_hosts?: string[]
  push?: Record<string, unknown>
  ki_nutzung?: Record<string, unknown>
  werkstatt_aktiv_tage?: number
  verlauf_tage?: number
  chat_max_tokens?: number
}

export interface DemoStartResult { ok: boolean; uebersprungen?: boolean; faelle: { aktenzeichen: string; schritte: number; fehler: string | null }[]; url: string }

export interface ChatModel { tag: string; label: string; parameter_size: string; size_bytes: number }
export interface ChatModelsResponse { router: string; router_ok: boolean; models: ChatModel[]; system: string }
export interface MerkenRequest {
  content: string
  category: string
  project?: string | null
  tags?: string[]
}
export interface MerkenResult {
  ok: boolean
  id: string | null
  weg: 'mcp' | 'api'
  hinweis?: string | null
}
export interface ChatSource {
  quelle: 'memory' | 'knowledge'
  titel: string
  text: string
  category: string | null
  project: string | null
  created_at: string | null
  score: number | null
  id: string | null
  /** Zitierkennung (Wissensbasis) oder Fundstelle */
  ref: string | null
}
export interface ChatStreamChunk {
  delta?: string; done?: boolean; error?: string
  /** Vor dem ersten Token: die herangezogenen Quellen aus Kira-RAG / Wissensbasis */
  sources?: ChatSource[]
  /** Hinweis, wenn die Suche nicht möglich war (Antwort kommt trotzdem, ohne Quellen) */
  rag_note?: string
  eval_count?: number | null; prompt_eval_count?: number | null; eval_duration_ms?: number; total_duration_ms?: number
}

export interface McpServerState {
  id: string; name: string; transport: 'http' | 'stdio'; url: string | null; command: string | null
  description: string; secret_key: string | null; secret_ok: boolean | null; header: string | null; snippet: string
  health: { ok: boolean | null; note: string } | null
  inspect: { ok: boolean; error: string | null; server: { name?: string; version?: string } | null; protocol?: string
    tools: { name: string; description: string }[]; skills: unknown } | null
  error?: string
}

export type AuftragStatus = 'eingang' | 'geplant' | 'laeuft' | 'rueckfrage' | 'freigabe' | 'fertig' | 'fehler' | 'abgebrochen'
export type AuftragProfil = 'lesen' | 'bearbeiten' | 'bearbeiten_tests' | 'voll'
export type AuftragAgent = 'claude' | 'codex' | 'gemini'
export type AuftragModus = 'bericht' | 'plan_freigabe' | 'umsetzen'
export type Zeitfenster = 'sofort' | 'nachts' | 'nach_reset'

export interface Auftrag {
  id: string; titel: string; text: string; host: string; projekt: string; projekt_name: string
  agent: AuftragAgent; modus: AuftragModus; profil: AuftragProfil; prioritaet: number; zeitfenster: Zeitfenster; status: AuftragStatus; reihenfolge: number
  branch: string | null; worktree: string | null; session_id: string | null; freigegeben: string | null
  gestartet: string | null; beendet: string | null; dauer_s: number | null
  ergebnis: string | null; fehler: string | null; kosten_usd: number | null; tokens_in: number | null; tokens_out: number | null; turns: number | null
  letzte_zeile: string | null; diff_url: string | null; erstellt: string; aktualisiert: string
}

export interface Kapazitaet {
  parallel_max: number; laufend: number; pause_grund: string | null; fuenf_stunden_pct: number | null; woche_pct: number | null; codex_woche_pct: number | null
}

export interface AuftraegeAntwort { auftraege: Auftrag[]; kapazitaet: Kapazitaet }
export interface LogZeile { ts: string | null; art: 'text' | 'tool' | 'result' | 'system' | 'fehler'; text: string }
export interface Projekt {
  host: string
  pfad: string
  name: string
  quelle: 'flow-agent' | 'werkstatt' | 'work_dirs'
  ausfuehrbar: boolean
  branch?: string | null
  dirty?: boolean
  technologien?: string[]
  graphify_stand?: string | null
}
export interface Vorlage { id: string; titel: string; modus: AuftragModus; profil: AuftragProfil; prioritaet: number; text: string }
