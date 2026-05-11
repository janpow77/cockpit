# Cockpit Admin API — Contract

Stand: 2026-05-11

Alle Endpoints unter `/admin/api/*`, JSON, Bearer-Auth (ausser `/health`, `/auth/login`).

## Auth
- `POST /admin/api/auth/login` `{password}` → `{token, expires_at}`
- `POST /admin/api/auth/logout` (auth) → 204
- `GET  /admin/api/auth/me` (auth) → `{logged_in, expires_at}`

## Health
- `GET /admin/api/health` (open) → `{status, version, started_at, uptime_s}`

## Dashboard
- `GET /admin/api/dashboard` (auth) → DashboardStats (apps_total, apps_healthy, apps_down, hosts_online, last_backup_at, recent_audit ...)

## Hosts
- `GET    /admin/api/hosts` → list
- `POST   /admin/api/hosts` `{name, tailscale_ip, ssh_user?, ssh_key_path?, is_self?}` → 201
- `GET    /admin/api/hosts/{id}` → detail
- `PATCH  /admin/api/hosts/{id}`
- `DELETE /admin/api/hosts/{id}`
- `GET    /admin/api/hosts/{id}/health` → forced health-check
- `GET    /admin/api/hosts/tailscale-status` → tailscale status JSON

## Apps
- `GET    /admin/api/apps` → list (mit host_name)
- `POST   /admin/api/apps` `{host_id, name, container_filter, compose_path?, healthcheck_url?}` → 201
- `GET    /admin/api/apps/{id}` → AppDetail mit containers[]
- `PATCH  /admin/api/apps/{id}`
- `DELETE /admin/api/apps/{id}`
- `POST   /admin/api/apps/{id}/health-check` → forced refresh
- `POST   /admin/api/apps/{id}/restart` → docker compose restart (mit Confirm im UI)
- `GET    /admin/api/apps/{id}/logs?tail=200` → `{logs: string}`

## GitHub (auth, 503 wenn GITHUB_TOKEN fehlt)
- `GET    /admin/api/github/repos` → bookmark-Liste
- `POST   /admin/api/github/repos` `{owner, name, default_branch?}` → 201
- `PATCH  /admin/api/github/repos/{id}`
- `DELETE /admin/api/github/repos/{id}`
- `GET    /admin/api/github/repos/{owner}/{name}/branches`
- `GET    /admin/api/github/repos/{owner}/{name}/prs?state=open`
- `GET    /admin/api/github/repos/{owner}/{name}/runs?limit=10`
- `GET    /admin/api/github/repos/{owner}/{name}/meta`
- `POST   /admin/api/github/repos/{owner}/{name}/dispatch` `{workflow_id, ref?, inputs?}` → 200

## Backups
- `GET    /admin/api/backups` → list
- `POST   /admin/api/backups` `{name, host_id, backup_type, command, target_path}` → 201
- `PATCH  /admin/api/backups/{id}`
- `DELETE /admin/api/backups/{id}`
- `POST   /admin/api/backups/{id}/run` → BackupRunResult
- `POST   /admin/api/backups/{id}/restore-test` → Phase-2-Stub

## Secrets / Vault (auth, 503 wenn COCKPIT_VAULT_KEY fehlt)
- `GET    /admin/api/secrets` → list (KEINE Werte)
- `POST   /admin/api/secrets` `{key, value, app_tag?, host_tag?, comment?}` → 201
- `PATCH  /admin/api/secrets/{id}` `{value?, app_tag?, host_tag?, comment?}`
- `DELETE /admin/api/secrets/{id}`
- `POST   /admin/api/secrets/{id}/reveal` `{purpose}` → `{key, value, revealed_at, purpose}` (Audit!)

## Audit (read-only)
- `GET /admin/api/audit?actor=&action=&target=&since=&limit=200` → list

## Settings
- `GET   /admin/api/settings` → SettingsOut
- `PATCH /admin/api/settings` `{health_interval_s?}`
