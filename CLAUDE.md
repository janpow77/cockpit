# cockpit

Zentrales Verwaltungs-Tool für ein Multi-App-/Multi-Host-Setup (Workshop, audit_designer,
llm-router/ai-router, flowinvoice, hpp, qaaudit u. a.). Bündelt Container-Status, Host-Health
(Tailscale/SSH), GitHub (Repos/PRs/CI), Backups, Deployments, Traffic und ein verschlüsseltes
Secret-Vault hinter einer Single-Admin-Oberfläche.

## Tech-Stack

- **Backend:** Python ≥ 3.12, FastAPI + Starlette, SQLAlchemy 2, uvicorn. SSH via paramiko,
  Vault-Verschlüsselung via cryptography (Fernet), httpx (GitHub-Client), PyYAML (Bootstrap-Config).
- **DB:** SQLite, Pfad `/data/cockpit.db` (Env `ADMIN_DB_PATH`, alternativ `ADMIN_DB_URL`).
- **Frontend:** Vue 3 SPA (Vite 6, Tailwind 4, Pinia, vue-router, axios, lucide-vue-next),
  TypeScript. Wird unter `/admin/` ausgeliefert (Router-Base `/admin/`).
- **API-Präfix:** alle Routen unter `/admin/api/*`; Health unter `/health` und `/admin/api/health`.
- **Auth:** Bearer-Token, Single-Admin (Session-Tokens in DB, `SessionRow`).
- **Port:** 7843 (Container `EXPOSE 7843`, uvicorn `--host 0.0.0.0 --port 7843`).
- **Deploy:** Docker (Multi-Stage: node:20-alpine Frontend-Build → python:3.12-slim Runtime,
  tini als PID 1, inkl. docker-CLI für Self-Host-Inspect), Compose-Standalone auf CCX23
  (Tailscale-only Bind `100.99.159.80:7843`).

## Setup & Befehle

Backend (lokal, via uv/pip):
```bash
pip install -e ".[dev]"                                    # FastAPI + dev (pytest, ruff)
uvicorn cockpit.main:app --reload --port 7843              # Dev-Server (Modul cockpit.main:app)
ruff check src                                             # Lint (Config in pyproject.toml)
pytest                                                     # testpaths=tests, asyncio_mode=auto
```

Frontend (`frontend/`, npm-Scripts aus package.json):
```bash
npm install
npm run dev          # Vite Dev-Server (proxyt /admin/api -> http://localhost:7843)
npm run build        # vue-tsc --noEmit + vite build
npm run build:nocheck# vite build ohne Type-Check (im Docker-Build genutzt)
npm run type-check   # vue-tsc --noEmit
npm run lint         # eslint . --ext .vue,.ts,.js --max-warnings=0
npm run test         # vitest run
```

Docker / Deploy:
```bash
docker build -t cockpit:v0.1 .                             # Multi-Stage-Build
docker compose -f compose.dev.yaml up -d                  # lokale Dev-Compose (Port 7843)
docker compose up -d                                       # Standalone (compose.yaml, CCX23)
```

Git-Hooks:
```bash
scripts/hooks/install.sh   # installiert pre-push (Ruff geänderter .py + Frontend-Build + pytest)
# SKIP_PREPUSH=1 / SKIP_PYTEST=1 / PYTEST_STRICT=1 steuern den Hook
```

## Struktur

```
src/cockpit/
  main.py        # FastAPI-App: mountet alle Router unter /admin/api/*, SPA unter /admin/,
                 #   Lifespan: init_db + Bootstrap + Health-Loop + Traffic-Collector
  auth.py        # Bearer-Token / Single-Admin (require_auth, issue/revoke/lookup_session, client_ip)
  db.py          # SQLite-Engine, get_session/get_session_factory, init_db
  config.py      # YAML-Bootstrap-Config laden (load_config), Env-Auswertung
  models.py      # SQLAlchemy-Modelle (HostRow, App-Rows, SettingRow, SessionRow, ...) + Mapper
  routes/        # FastAPI-Router je Domäne: auth, dashboard, hosts, apps, github, backups,
                 #   secrets, audit, settings, traffic, deployments
  crud/          # DB-Zugriffe je Domäne (apps, hosts, github_repos, backups, secrets,
                 #   deployments, traffic, audit)
  services/      # ssh_runner (run_on_host), docker_inspect, tailscale, health_check,
                 #   github_client, backup_runner, secret_vault, caddy_log,
                 #   traffic_collector, bootstrap
frontend/src/
  api/           # axios-Clients je Domäne + client.ts (Basis), types.ts
  views/         # Seiten je Domäne (Dashboard, hosts, apps, github, traffic,
                 #   deployments, backups, secrets, audit, settings, LoginView)
  components/    # layout/ (AppShell, Sidebar, TopBar) + shared/ (Card, Modal, Toasts, ...)
  stores/        # Pinia: auth, theme, toast, poll, confirm
  router/        # vue-router, Base /admin/, Auth-Guard (beforeEach)
docs/            # Sanierungs-/Konsistenz-Pläne, System-Landschaft, Tailscale-Fallback
scripts/         # hooks/ (pre-push + install.sh), notify-deployment.sh
graphify-out/    # generierte Abhängigkeitsgraphen (graph.json/html, manifest, analysis)
```

Zentrale Module (aus dem Abhängigkeitsgraphen, höchster Grad): `auth.client_ip`,
`auth.require_auth`, `services.ssh_runner.run_on_host`, `db.get_session` / `db.init_db`,
`models.app_row_to_out` / `models.HostRow`.

## Konventionen

- **Lint/Format:** ruff (`line-length = 110`, `target-version = py312`, Regeln `E,F,I,B,UP,N`;
  ignoriert `E501`, `B008` — FastAPI `Depends()` im Default-Arg ist idiomatisch). Frontend: eslint
  mit `--max-warnings=0`, vue-tsc Type-Check.
- **Tests:** pytest mit `asyncio_mode = auto`, `testpaths = tests` (Verzeichnis derzeit leer);
  Frontend vitest + @vue/test-utils + happy-dom.
- **Sprache:** Code-Kommentare, Docstrings und UI deutsch.
- **Auth-Hinweis:** `/admin/api/*` ist hinter `require_auth` (Bearer-Token); SPA-Catch-All in
  `main.py` schützt `api/`-Pfade vor dem Fallback auf `index.html`.
