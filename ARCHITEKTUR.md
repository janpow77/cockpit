# Architektur — wt-a_323013db73

_Automatisch generiert von graphify-kira aus dem Code-Graphen. Nicht von Hand editieren — wird beim nächsten Lauf überschrieben._

**Umfang:** 1786 Knoten, 3977 Kanten, 20 größere Module, 0 zirkuläre Abhängigkeiten.

## Modulkarte

- **Community 0** (91): `__init__.py`, `auth.py`, `datetime`, `Session`, `config.py`
- **Community 1** (78): `WallView.vue`
- **Community 2** (78): `models.py`, `auftraege.py`, `datetime`, `Session`, `auftrag_runner.py`
- **Community 3** (73): `traffic.py`, `Session`, `TrafficSourceCreate`, `datetime`, `Base`
- **Community 4** (67): `audit.py`, `Any`, `Session`, `models.py`, `auftraege.py`
- **Community 5** (56): `github_repos.py`, `Session`, `RepoCreate`, `models.py`, `github.py`
- **Community 6** (51): `KanbanView.vue`
- **Community 7** (47): `apps.ts`, `hosts.ts`, `types.ts`, `DashboardView.vue`, `AppDetailView.vue`
- **Community 8** (45): `types.ts`, `ChatView.vue`
- **Community 9** (43): `traffic.ts`, `types.ts`, `TrafficView.vue`
- **Community 10** (41): `overview.ts`, `WallSettingsCard.vue`
- **Community 11** (35): `overview.py`, `Session`, `Any`, `WallConfig`, `get`
- **Community 12** (34): `audit.ts`, `auth.ts`, `backups.ts`, `client.ts`, `mcp.ts`
- **Community 13** (33): `overview.ts`, `types.ts`, `WallSettingsCard.vue`
- **Community 14** (32): `audit.ts`, `Badge.vue`, `format.ts`, `DashboardView.vue`, `AuditView.vue`
- **Community 15** (31): `tsconfig.json`
- **Community 16** (31): `auth.py`, `Request`, `__init__.py`, `deployments.py`, `Session`
- **Community 17** (31): `overview.py`, `push.py`, `datetime`, `wall_loop.py`, `WallConfig`
- **Community 18** (29): `models.py`, `BaseModel`, `field_validator`, `datetime`, `audit.py`
- **Community 19** (28): `secrets.py`, `Session`, `SecretCreate`, `models.py`, `secret_vault.py`

## Zentrale Bausteine (God Nodes)

_Hohe Zentralität ist nicht automatisch ein Defekt (zentrale Stores/Modelle sind oft legitim). Konkrete Refactoring-Prioritäten siehe Optimierungs-Report._

- `Base` — Grad 13 (ein 13/aus 0)
- `extractError() (frontend/src/api/client.ts)` — Grad 81 (ein 81/aus 0)
- `KanbanView.vue (frontend/src/views/KanbanView.vue)` — Grad 110 (ein 0/aus 110)
- `WallView.vue (frontend/src/views/WallView.vue)` — Grad 104 (ein 0/aus 104)
- `models.py (src/cockpit/models.py)` — Grad 96 (ein 36/aus 60)
- `types.ts (frontend/src/api/types.ts)` — Grad 99 (ein 34/aus 65)
- `HostRow (src/cockpit/models.py)` — Grad 52 (ein 51/aus 1)
- `BaseModel` — Grad 33 (ein 33/aus 0)
- `ChatView.vue (frontend/src/views/ChatView.vue)` — Grad 83 (ein 0/aus 83)
- `TrafficView.vue (frontend/src/views/traffic/TrafficView.vue)` — Grad 60 (ein 0/aus 60)

## Schnittstellen / Brücken (Betweenness)

- `models.py (src/cockpit/models.py)` — Betweenness 0.001
- `overview.py (src/cockpit/routes/overview.py)` — Betweenness 0.001
- `test_wall.py (tests/test_wall.py)` — Betweenness 0.001
- `types.ts (frontend/src/api/types.ts)` — Betweenness 0.001
- `routes/traffic.py (src/cockpit/routes/traffic.py)` — Betweenness 0.000
- `stores/auth.ts (frontend/src/stores/auth.ts)` — Betweenness 0.000
- `mock.ts (frontend/src/api/mock.ts)` — Betweenness 0.000
- `api/auth.ts (frontend/src/api/auth.ts)` — Betweenness 0.000
- `routes/secrets.py (src/cockpit/routes/secrets.py)` — Betweenness 0.000
- `cockpit/auth.py (src/cockpit/auth.py)` — Betweenness 0.000

## Empfohlene Spezialisten

Passend zu Stack/Domäne dieses Projekts (Claude-Code-Agents/Skills):

`/deutsche-formulierung`, `@git-workflow`, `/auto-verify`, `@code-api-checker`, `@code-audit-expert`, `@docker-proxy-debugger`, `/docker-debug`, `/cross-project-health`, `@e2e-browser-tester`, `/modern-gui-builder`, `/ux-completeness-check`, `/vue3-gui-builder`, `/mcp-server-expert`.

## Hinweis für Änderungen

Vor dem Ändern eines zentralen Bausteins die Abhängigen prüfen — am schnellsten über den **graphify-MCP** (globaler Graph): „Was hängt an `<datei>`?". Brücken-Knoten stabil halten.

