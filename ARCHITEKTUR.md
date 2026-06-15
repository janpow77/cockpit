# Architektur — cockpit

_Automatisch generiert von graphify-kira aus dem Code-Graphen. Nicht von Hand editieren — wird beim nächsten Lauf überschrieben._

**Umfang:** 702 Knoten, 1421 Kanten, 20 größere Module, 0 zirkuläre Abhängigkeiten.

## Modulkarte

- **Data Models & Audits** (65): `models.py`, `BaseModel`, `audit.py`, `dashboard.py`, `hosts.py`
- **Backup & Deployment** (58): `models.py`, `backup_runner.py`, `docker_inspect.py`, `health_check.py`, `ssh_runner.py`
- **Authentication System** (45): `auth.py`, `models.py`, `deployments.py`
- **App Management** (42): `auth.py`, `models.py`, `apps.py`, `github.py`
- **Audit Logging** (42): `__init__.py`, `audit.py`, `backups.py`, `deployments.py`, `Base`
- **Database Setup** (35): `db.py`, `models.py`, `__init__.py`, `RuntimeError`, `traffic_collector.py`
- **Cockpit Config** (34): `__init__.py`, `config.py`, `main.py`, `models.py`, `settings.py`
- **Frontend Dependencies** (31): `package.json`
- **Dashboard Components** (26): `audit.ts`, `client.ts`, `dashboard.ts`, `mock.ts`, `settings.ts`
- **App CRUD** (26): `apps.py`, `models.py`, `bootstrap.py`
- **TypeScript Config** (23): `tsconfig.json`
- **Traffic Source Management** (22): `models.py`, `traffic.py`
- **Traffic Source CRUD** (21): `traffic.py`, `models.py`
- **Authentication Client** (19): `App.vue`, `auth.ts`, `client.ts`, `main.ts`, `index.ts`
- **Backup Management** (17): `models.py`, `backups.py`
- **GitHub Repo Management** (16): `github_repos.py`, `models.py`
- **Traffic Data Handling** (15): `traffic.ts`, `types.ts`
- **Deployment Records** (14): `deployments.ts`, `types.ts`
- **Host Management** (14): `hosts.py`
- **GitHub API Client** (14): `github_client.py`

## Zentrale Bausteine (God Nodes)

_Hohe Zentralität ist nicht automatisch ein Defekt (zentrale Stores/Modelle sind oft legitim). Konkrete Refactoring-Prioritäten siehe Optimierungs-Report._

- `BaseModel` — Grad 33 (ein 33/aus 0)
- `models.py (src/cockpit/models.py)` — Grad 83 (ein 25/aus 58)
- `Base` — Grad 11 (ein 11/aus 0)
- `SessionRow (src/cockpit/models.py)` — Grad 8 (ein 7/aus 1)
- `client_ip() (src/cockpit/auth.py)` — Grad 31 (ein 30/aus 1)
- `auth.py (src/cockpit/auth.py)` — Grad 31 (ein 11/aus 20)
- `types.ts (frontend/src/api/types.ts)` — Grad 31 (ein 10/aus 21)
- `mock.ts (frontend/src/api/mock.ts)` — Grad 29 (ein 8/aus 21)
- `main.py (src/cockpit/main.py)` — Grad 28 (ein 1/aus 27)
- `db.py (src/cockpit/db.py)` — Grad 25 (ein 15/aus 10)

## Schnittstellen / Brücken (Betweenness)

- `models.py (src/cockpit/models.py)` — Betweenness 0.005
- `main.py (src/cockpit/main.py)` — Betweenness 0.002
- `auth.py (src/cockpit/auth.py)` — Betweenness 0.001
- `traffic.py (src/cockpit/routes/traffic.py)` — Betweenness 0.001
- `apps.py (src/cockpit/crud/apps.py)` — Betweenness 0.001
- `github.py (src/cockpit/routes/github.py)` — Betweenness 0.001
- `deployments.py (src/cockpit/routes/deployments.py)` — Betweenness 0.001
- `db.py (src/cockpit/db.py)` — Betweenness 0.001
- `auth.py (src/cockpit/routes/auth.py)` — Betweenness 0.001
- `bootstrap.py (src/cockpit/services/bootstrap.py)` — Betweenness 0.001

## Empfohlene Spezialisten

Passend zu Stack/Domäne dieses Projekts (Claude-Code-Agents/Skills):

`/deutsche-formulierung`, `@git-workflow`, `/auto-verify`, `@code-api-checker`, `@code-audit-expert`, `@docker-proxy-debugger`, `/docker-debug`, `/cross-project-health`, `@e2e-browser-tester`, `/modern-gui-builder`, `/ux-completeness-check`, `/vue3-gui-builder`.

## Hinweis für Änderungen

Vor dem Ändern eines zentralen Bausteins die Abhängigen prüfen — am schnellsten über den **graphify-MCP** (globaler Graph): „Was hängt an `<datei>`?". Brücken-Knoten stabil halten.

