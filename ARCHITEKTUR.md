# Architektur — cockpit

_Automatisch generiert von graphify-kira aus dem Code-Graphen. Nicht von Hand editieren — wird beim nächsten Lauf überschrieben._

**Umfang:** 741 Knoten, 1523 Kanten, 20 größere Module, 0 zirkuläre Abhängigkeiten.

## Modulkarte

- **main.py** (71): `__init__.py`, `config.py`, `db.py`, `main.py`, `models.py`
- **crud/secrets.py** (46): `RuntimeError`, `secrets.py`, `Session`, `SecretRow`, `SecretUpdate`
- **cockpit/auth.py** (45): `auth.py`, `models.py`, `deployments.py`
- **models.py** (43): `models.py`, `Base`, `BaseModel`, `audit.py`
- **docker_inspect.py** (43): `backup_runner.py`, `docker_inspect.py`, `ssh_runner.py`
- **routes/traffic.py** (42): `traffic.py`, `models.py`
- **client_ip** (38): `auth.py`, `models.py`, `apps.py`, `backups.py`
- **github.py** (37): `github_repos.py`, `models.py`, `github.py`
- **traffic_collector.py** (31): `models.py`, `__init__.py`, `caddy_log.py`, `traffic_collector.py`
- **crud/apps.py** (27): `apps.py`, `models.py`, `bootstrap.py`
- **crud/audit.py** (25): `__init__.py`, `audit.py`, `deployments.py`, `models.py`
- **SecretsView.vue** (24): `secrets.ts`, `SecretsView.vue`
- **compilerOptions** (23): `tsconfig.json`
- **routes/hosts.py** (22): `models.py`, `hosts.py`, `tailscale.py`
- **stores.test.ts** (21): `App.vue`, `main.ts`, `index.ts`, `auth.ts`, `confirm.ts`
- **types.ts** (19): `dashboard.ts`, `deployments.ts`, `types.ts`
- **client.ts** (16): `audit.ts`, `auth.ts`, `client.ts`, `types.ts`
- **mock.ts** (16): `mock.ts`, `settings.ts`, `types.ts`
- **traffic.ts** (15): `traffic.ts`, `types.ts`
- **crud/backups.py** (15): `backups.py`, `models.py`

## Zentrale Bausteine (God Nodes)

_Hohe Zentralität ist nicht automatisch ein Defekt (zentrale Stores/Modelle sind oft legitim). Konkrete Refactoring-Prioritäten siehe Optimierungs-Report._

- `BaseModel` — Grad 33 (ein 33/aus 0)
- `models.py (src/cockpit/models.py)` — Grad 83 (ein 25/aus 58)
- `Base` — Grad 11 (ein 11/aus 0)
- `SessionRow (src/cockpit/models.py)` — Grad 8 (ein 7/aus 1)
- `client_ip() (src/cockpit/auth.py)` — Grad 31 (ein 30/aus 1)
- `cockpit/auth.py (src/cockpit/auth.py)` — Grad 31 (ein 11/aus 20)
- `types.ts (frontend/src/api/types.ts)` — Grad 31 (ein 10/aus 21)
- `RuntimeError` — Grad 4 (ein 4/aus 0)
- `mock.ts (frontend/src/api/mock.ts)` — Grad 29 (ein 8/aus 21)
- `main.py (src/cockpit/main.py)` — Grad 28 (ein 1/aus 27)

## Schnittstellen / Brücken (Betweenness)

- `models.py (src/cockpit/models.py)` — Betweenness 0.005
- `main.py (src/cockpit/main.py)` — Betweenness 0.002
- `routes/traffic.py (src/cockpit/routes/traffic.py)` — Betweenness 0.001
- `cockpit/auth.py (src/cockpit/auth.py)` — Betweenness 0.001
- `traffic_collector.py (src/cockpit/services/traffic_collector.py)` — Betweenness 0.001
- `dashboard.py (src/cockpit/routes/dashboard.py)` — Betweenness 0.001
- `crud/apps.py (src/cockpit/crud/apps.py)` — Betweenness 0.001
- `ssh_runner.py (src/cockpit/services/ssh_runner.py)` — Betweenness 0.001
- `github_repos.py (src/cockpit/crud/github_repos.py)` — Betweenness 0.001
- `crud/audit.py (src/cockpit/crud/audit.py)` — Betweenness 0.001

## Empfohlene Spezialisten

Passend zu Stack/Domäne dieses Projekts (Claude-Code-Agents/Skills):

`/deutsche-formulierung`, `@git-workflow`, `/auto-verify`, `@code-api-checker`, `@code-audit-expert`, `@docker-proxy-debugger`, `/docker-debug`, `/cross-project-health`, `@e2e-browser-tester`, `/modern-gui-builder`, `/ux-completeness-check`, `/vue3-gui-builder`.

## Hinweis für Änderungen

Vor dem Ändern eines zentralen Bausteins die Abhängigen prüfen — am schnellsten über den **graphify-MCP** (globaler Graph): „Was hängt an `<datei>`?". Brücken-Knoten stabil halten.

