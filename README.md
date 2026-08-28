# cockpit

Zentrales Verwaltungs-Tool für Multi-App-Multi-Host-Setup
(Workshop, audit_designer, llm-router, flowinvoice, hpp, qaaudit, ...).

## Domänen (Phase 1)

1. **Apps** — Container-Status pro Host (NUC/CCX23/evo), Logs, Restart
2. **Hosts** — Tailscale-Health, SSH-Reachability
3. **GitHub** — Repos, PRs, CI-Runs (via GITHUB_TOKEN)
4. **Backups** — Job-Liste, On-Demand-Run, Restore-Test
5. **Secrets / Vault** — verschlüsselt at-rest (Fernet), jede Reveal im Audit

## Stack

- FastAPI + SQLAlchemy + SQLite (`/data/cockpit.db`)
- Vue 3 SPA unter `/admin/` (vite + tailwind 4 + pinia)
- Bearer-Token-Auth (Single-Admin)
- paramiko für SSH-Befehle, lokale subprocess auf CCX23
- Docker Compose Standalone-Deploy

## Deploy

Lokal:
```bash
docker build -t cockpit:v0.1 .
docker compose up -d
```

CCX23 (intern, Tailscale-only):
```bash
# image scp + auf CCX23 importieren + compose up
docker save cockpit:v0.1 | gzip | ssh deploy@100.99.159.80 'gunzip | docker load'
ssh deploy@100.99.159.80 'cd /opt/cockpit && docker compose up -d'
# Zugriff: http://100.99.159.80:7843/admin/
```

## Env

```
COCKPIT_ADMIN_PASSWORD=<bcrypt-or-plain>   # default: cockpit-admin (mit warn)
COCKPIT_VAULT_KEY=<fernet-key>             # 32-byte url-safe-base64
GITHUB_TOKEN=<gh-pat>                      # optional, ohne: GitHub-Endpoints leer
ADMIN_DB_PATH=/data/cockpit.db
COCKPIT_PORT=7843
```
