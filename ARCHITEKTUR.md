# Architektur — cockpit

_Automatisch generiert von graphify-kira aus dem Code-Graphen. Nicht von Hand editieren — wird beim nächsten Lauf überschrieben._

**Umfang:** 1983 Knoten, 3693 Kanten, 20 größere Module, 0 zirkuläre Abhängigkeiten.

## Modulkarte

- **WallView.vue** (78): `WallView.vue`, `types.ts`
- **KanbanView.vue** (58): `auftraege.ts`, `labels.ts`, `KanbanView.vue`
- **crud/traffic.py** (51): `__init__.py`, `traffic_collector.py`, `traffic.py`, `Session`, `datetime`
- **models.py** (49): `Base`, `audit.py`, `bootstrap.py`, `BaseModel`, `datetime`
- **ChatView.vue** (47): `types.ts`, `ChatView.vue`
- **crud/secrets.py** (46): `RuntimeError`, `secrets.py`, `Session`, `SecretRow`, `SecretUpdate`
- **WallSettingsCard.vue** (46): `overview.ts`, `WallSettingsCard.vue`
- **labels.ts** (44): `auftraege.ts`, `AuftragDetail.vue`, `AuftragFormular.vue`, `AuftragKarte.vue`, `AuftragSpalte.vue`
- **crud/hosts.py** (43): `__init__.py`, `deployments.py`, `hosts.py`, `Request`, `Session`
- **routes/auftraege.py** (43): `auftraege.py`, `BaseModel`, `Session`, `WallConfig`
- **crud/backups.py** (42): `backups.py`, `backup_runner.py`, `ssh_runner.py`, `models.py`
- **telegram_dialog.py** (41): `auftrag_vorlagen.py`, `Session`, `WallConfig`, `Event`, `telegram_dialog.py`
- **wall_config.py** (36): `mcp.py`, `Session`, `mcp_client.py`, `Response`, `Client`
- **test_auftraege.py** (35): `test_auftraege.py`
- **types.ts** (33): `mcp.ts`, `chat.ts`, `FlowAgentKachel.vue`, `types.ts`
- **auftraege.ts** (32): `auftraege.ts`, `KanbanView.vue`, `types.ts`
- **TrafficView.vue** (31): `TrafficView.vue`
- **flow_agent.py** (30): `flow_agent.py`
- **overview.py** (29): `BaseModel`, `Session`, `overview.py`
- **mock.ts** (27): `audit.ts`, `dashboard.ts`, `mock.ts`, `settings.ts`, `client.ts`

## Zentrale Bausteine (God Nodes)

_Hohe Zentralität ist nicht automatisch ein Defekt (zentrale Stores/Modelle sind oft legitim). Konkrete Refactoring-Prioritäten siehe Optimierungs-Report._

- `Base` — Grad 14 (ein 14/aus 0)
- `types.ts (frontend/src/api/types.ts)` — Grad 112 (ein 46/aus 66)
- `KanbanView.vue (frontend/src/views/KanbanView.vue)` — Grad 118 (ein 0/aus 118)
- `extractError() (frontend/src/api/client.ts)` — Grad 66 (ein 66/aus 0)
- `WallView.vue (frontend/src/views/WallView.vue)` — Grad 110 (ein 0/aus 110)
- `models.py (src/cockpit/models.py)` — Grad 91 (ein 30/aus 61)
- `BaseModel` — Grad 33 (ein 33/aus 0)
- `AuftragRow (src/cockpit/models.py)` — Grad 37 (ein 36/aus 1)
- `ChatView.vue (frontend/src/views/ChatView.vue)` — Grad 75 (ein 0/aus 75)
- `services/auftraege.py (src/cockpit/services/auftraege.py)` — Grad 64 (ein 4/aus 60)

## Schnittstellen / Brücken (Betweenness)

- `types.ts (frontend/src/api/types.ts)` — Betweenness 0.001
- `services/auftraege.py (src/cockpit/services/auftraege.py)` — Betweenness 0.001
- `models.py (src/cockpit/models.py)` — Betweenness 0.001
- `wall_loop.py (src/cockpit/services/wall_loop.py)` — Betweenness 0.000
- `routes/deployments.py (src/cockpit/routes/deployments.py)` — Betweenness 0.000
- `telegram_dialog.py (src/cockpit/services/telegram_dialog.py)` — Betweenness 0.000
- `client.ts (frontend/src/api/client.ts)` — Betweenness 0.000
- `crud/hosts.py (src/cockpit/crud/hosts.py)` — Betweenness 0.000
- `cockpit/auth.py (src/cockpit/auth.py)` — Betweenness 0.000
- `flow_agent.py (src/cockpit/services/flow_agent.py)` — Betweenness 0.000

## Empfohlene Spezialisten

Passend zu Stack/Domäne dieses Projekts (Claude-Code-Agents/Skills):

`/deutsche-formulierung`, `@git-workflow`, `/auto-verify`, `@code-api-checker`, `@code-audit-expert`, `@docker-proxy-debugger`, `/docker-debug`, `/cross-project-health`, `@e2e-browser-tester`, `/modern-gui-builder`, `/ux-completeness-check`, `/vue3-gui-builder`, `/mcp-server-expert`.

## Hinweis für Änderungen

Vor dem Ändern eines zentralen Bausteins die Abhängigen prüfen — am schnellsten über den **graphify-MCP** (globaler Graph): „Was hängt an `<datei>`?". Brücken-Knoten stabil halten.

