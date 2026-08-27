# Wand, KI-Konsole und MCP-Einstellungen – Umsetzungsplan

> Stand: 27.08.2026 · Status: **in Umsetzung** · Anlass: HPP-Vorführung (Woche ab 31.08.2026)
> Aufbauend auf `m18-overview-widget-plan.md` (Read-only-Aggregat, Handeln in den Admin-UIs).

## 1. Ziele

1. **Wand** (`/admin/wall`): Vollbild-Ansicht, die während der Vorführung „zufällig" im
   Hintergrund läuft – oben die **Landschaft** (Hosts als Knoten, Tailscale-Mesh,
   Cloudflare-Rand mit den öffentlichen Diensten, fließender Verkehr), direkt darunter der
   **Leitstand** (Hosts mit Load/RAM/Disk, alle Compose-Projekte je Host, Sonden, Sicherungen,
   lokale Modelle, GitHub), unten das **Laufband** (Commits, Deploys, Audit).
2. **HPP-Demo direkt starten**: Der Hero-Knopf meldet sich mit Vault-Zugang am HPP an, baut
   die Demo-Fälle neu auf und öffnet die Demo-Seite.
3. **KI-Konsole** (`/admin/chat`): Chat mit lokalen Modellen über den ai-router
   (Standard `qwen3.8-heretic:27b`, Whitelist mit Anzeigenamen), Streaming, kein Verlauf
   auf dem Server.
4. **MCP-Einstellungen** (`/admin/mcp`): die MCP-Server der Landschaft mit Erreichbarkeit,
   Werkzeugliste, Skills und der fertigen Verbindungskonfiguration für Claude Code;
   Zugangsdaten bleiben im Vault.
5. **Zugriff**: cockpit bleibt Tailscale-only (`100.99.159.80:7843`). Der MacBook Air ist
   Tailscale-Host – die Wand ist damit am Vortragsort erreichbar, ohne das cockpit öffentlich
   zu machen. Fallback: Handy-Hotspot.

## 2. Architektur (Backend)

| Baustein | Datei | Aufgabe |
|---|---|---|
| Host-Kennzahlen | `services/host_stats.py` | Ein Shell-Befehl je Host (Load, RAM, Disk, Uptime, Container), 45 s Cache |
| Projekt-Entdeckung | `services/docker_inspect.py` → `projects_on_host()` | `docker ps` je Host, Gruppierung nach Compose-Projekt (Label), Status je Projekt |
| ai-router | `services/ai_router_client.py` | `/api/tags` (Modelle), `/api/chat` (Streaming) |
| GitHub | `services/github_client.py` → `list_user_repos`, `list_repo_commits` | alle Repos des Kontos, jüngste Commits (nur mit `GITHUB_TOKEN`) |
| Wand-Konfiguration | `services/wall_config.py` | JSON in `cockpit_settings` (Schlüssel `wall`): Ausblendliste, Links, Labels, Hero, Sonden, Demo, Sicherungspfad, Modell-Whitelist, Systemprompt |
| Aggregat | `routes/overview.py` | `GET /admin/api/overview`, `GET/PATCH …/config`, `POST …/demo` |
| Chat | `routes/chat.py` | `GET /admin/api/chat/models`, `POST /admin/api/chat` (SSE) |
| MCP | `services/mcp_client.py`, `routes/mcp.py` | `GET /admin/api/mcp/servers` (Health, tools/list, Skills), Konfigurationsvorlage |

Grundsätze: alles lesend außer `POST /demo` (Audit-Eintrag), keine Secrets an den Client,
jede Fremdquelle mit Timeout und ohne Ausnahme nach außen (die Wand fällt nie aus, sie
zeigt „nicht erreichbar").

### Sonden

Generische JSON-Endpunkte, deren Felder als Kennzahlen erscheinen. Der Schlüssel liegt im
Vault und wird serverseitig als Header gesetzt:

| id | URL | Vault-Schlüssel | Header |
|---|---|---|---|
| `hpp` | `https://hpp.flowaudit.de/api/kpang/vollzug/stats` | `hpp_token` | `Authorization: Bearer …` |
| `kira` | `https://mcp.flowaudit.de/api/memory/stats` | `memory_api_key` | `X-Memory-API-Key` |

### Demo-Start

`POST /admin/api/overview/demo` → Anmeldung `https://hpp.flowaudit.de/api/auth/login` mit den
Vault-Secrets `hpp_demo_user` / `hpp_demo_password` (HPP-Benutzer mit Admin-Rolle) →
`POST /api/kpang/vollzug/demo/aufbauen` → Ergebnis je Fall → Frontend öffnet
`https://hpp.flowaudit.de/kraftstoff/vollzug/demo`.

## 3. Frontend

| Route | Datei | Bemerkung |
|---|---|---|
| `/wall` | `views/WallView.vue` | Vollbild ohne Sidebar, dunkle Tokens, Tasten `F` (Vollbild) und `R` (Aktualisieren), Poll 30 s |
| `/chat` | `views/ChatView.vue` | Modellwahl, Systemprompt, Streaming, Stopp, Markdown-light |
| `/mcp` | `views/mcp/McpView.vue` | Serverliste, Werkzeuge, Skills, Konfigurationsvorlage zum Kopieren |
| `/settings` | Karte „Wand & KI-Konsole" | Ausblendliste, Links, Hero, Sonden, Demo, Modelle, Systemprompt (JSON-Felder mit Prüfung) |

Design der Wand: Grund `#0B1020`, Flächen `#131A2E`/`#1A2340`, Linien `#263054`, Text
`#E7ECF7`, Akzent Bernstein `#F2B84B` (nur Blickfang), Status getrennt (Grün `#4CC38A`,
Bernstein, Rot `#F26D6D`). Schrift Barlow Condensed (Titel), IBM Plex Sans (Text), IBM Plex
Mono (Zahlen). Animation: pulsierende Statusringe, fließende Kanten, hochzählende Kennzahlen,
gestaffelte Einblendung, Laufband – alles aus unter „Bewegung reduzieren".

## 4. Sichtbarkeit (Whitelist/Ausblendung)

Auf die Wand kommt nur, was nicht in `wall.hide` steht (Teilstring, Groß/Klein egal).
Vorgabe: `love-ai, x_chat, sarah, kino, mediaarchiv, portainer, buildx_buildkit, watchtower`.
Vault, Secrets, Audit-Details und Traffic-Rohdaten erscheinen nie. Hosts optional per
`wall.hosts` einschränken.

## 5. Deploy und Betrieb

1. Image `cockpit:v0.3` bauen (Multi-Stage), `docker save | ssh … docker load`.
2. `/opt/cockpit/compose.yaml`: Image-Tag, zusätzliches Mount
   `/home/deploy/backups:/backups:ro` (Sicherungsstand auf der Wand).
3. Env `/etc/cockpit/env`: optional `GITHUB_TOKEN` (alle Repos + Commits), optional
   `AI_ROUTER_URL` (Standard `http://100.99.159.80:7842`).
4. Registrierung kuratieren: HPP auf ccx23 (`name=hpp-`, Health `https://hpp.flowaudit.de/api/health`),
   flowinvoice/checklist/auditworkshop/ai-router auf ccx23 prüfen.
5. Vault: `hpp_demo_user`, `hpp_demo_password`, `hpp_token`, `memory_api_key`,
   `mcp_flowaudit_token` anlegen (nur der Nutzer).
6. Prüfung: Wand im Browser (Playwright), Chat-Antwort vom Router, Demo-Start gegen HPP.

## 6. Sicherheit

Tailscale-only, keine öffentliche Freigabe; Bearer-Auth wie bisher; Secrets nur
serverseitig entschlüsselt; Demo-Start und Konfigurationsänderungen im Audit; Whitelist
verhindert, dass Privates auf einer Vorführwand landet.

## 7. Offene Entscheidungen (Nutzer)

- `GITHUB_TOKEN` in `/etc/cockpit/env` eintragen (read-only PAT reicht) – sonst bleibt die
  GitHub-Kachel leer.
- Vault-Secrets anlegen (siehe 5.).
- Modellname: `qwen3.8-heretic:27b` erscheint in der Konsole als „Qwen 3.8 · 27B"; die
  Modellliste ist eine Whitelist – ungeeignete Tags (uncensored/sarah) sind ausgeblendet.
- MacBook: Tailscale eingeschaltet, Anmeldung am cockpit mit dem Admin-Passwort.

## 8. Arbeitsfolge

1. Backend (host_stats, Discovery, ai-router, Overview, Chat, Wand-Konfiguration) ✔
2. Wand-View ✔ · KI-Konsole (Codex) · MCP-Client und -Seite · Einstellungen-Karte
3. Lokaler Testlauf (Backend auf der NUC gegen echte Hosts, Frontend-Build, Browser)
4. Deploy ccx23, Registrierung kuratieren, Prüfung vom MacBook (Tailscale)

## 9. Mehrwert-Bausteine (Stand 27.08.2026)

Die Wand ist nicht nur Schaufenster, sondern Arbeitsmittel. Vier Bausteine kommen
serverseitig dazu (`services/wall_extras.py`, im selben `GET /admin/api/overview`,
alle 30 s vom Frontend geholt, jeder Sammler fehlertolerant):

| Baustein | Was er liefert | Woher |
| --- | --- | --- |
| **Handlungsbedarf** | kritisch/prüfen/Hinweis: Host offline, Platte ≥ 80/90 %, RAM ≥ 92 %, Last > 1,5 × CPUs, registrierte/öffentliche Projekte mit gestoppten Containern, Sicherung > 30/72 h, Dienst ohne Antwort, TLS < 14/7 Tage, langsame Antwort > 3 s, ai-router aus, Pausen jünger als 7 Tage | reine Ableitung `handlungsbedarf()` (getestet) |
| **Öffentliche Dienste** | je Adresse aus `links` + Hero: HTTP-Status, Antwortzeit, TLS-Restlaufzeit und Aussteller (10 min gecacht), Zugriffe der letzten 24 h als Stundenverlauf aus den Caddy-Samples | `dienste_pruefen()` + `crud.traffic.series` |
| **Werkstatt** | je Host aus `work_dirs`: Branch, uncommittete Änderungen, nicht gepushte Commits, letzter Commit, `.session_resume.md` (Pause) samt „Nächster Schritt“-Zeile; jüngste Aktivität zuerst | ein Shell-Durchlauf per SSH (`werkstatt_cmd`), 3 min Cache, stale-while-revalidate |
| **Kira · zuletzt gelernt** | Gesamtzahl und die jüngsten Wissenseinträge (architecture, solution, reference …; `session_log`/`transcript` bleiben weg) | `curl` auf dem NUC per SSH; Schlüssel aus dessen `.env` (`kira.env_file`), verlässt den Host nie |

Gestoppte Entwicklungs-Stacks auf dem NUC lösen keinen Alarm aus: Es zählen nur
registrierte Apps, Instanzen mit eigenem Tunnel und – auf dem Self-Host (Produktion) –
Projekte mit öffentlicher Adresse. Laptop aus (`macbook`) ist ein Hinweis, kein Alarm.

Neue Einstellungen (`wall`): `work_dirs` (Host → Verzeichnis; Self-Host ccx23 nutzt
den Read-only-Mount `/work/ccx23`), `kira` (host, url, env_file, env_key). Die
Modell-Whitelist der Konsole ist bewusst kurz (Qwen 3.8 · 27B, Qwen 3.5 · 35B); flow-agent-
und EVO-Modelle des Routers erscheinen nicht.

Betrieb: `compose.yaml` bindet zusätzlich `/home/deploy/Projekte:/work/ccx23:ro` und
`/home/deploy/backups:/backups:ro`; das Image enthält `git`. Der Ticker führt Alarme
und Kira-Einträge vor den Ereignissen. Kopfzeile zeigt LIVE mit Sekunden seit dem
letzten Stand; `R` lädt sofort, `F` schaltet Vollbild.

## 10. Zugänge und Secrets (Stand 27.08.2026, eingerichtet)

| Zweck | Wo | Wert |
| --- | --- | --- |
| Demo-Start von der Wand | Vault `hpp_demo_user` / `hpp_demo_password` | HPP-Prod-Benutzer `cockpit-demo` (Rolle admin), Passwort nur auf dem Hetzner in `/home/deploy/.hpp_cockpit_demo_pw` |
| HPP-Kennzahlen (Sonde) | Vault `hpp_smoke_user` / `hpp_smoke_password` | lesender Account `claude-smoke`; die Sonde meldet sich über `login_url` an (Token 30 min), kein Dauer-Token |
| MCP flowaudit (Werkzeuge/Skills) | Vault `mcp_flowaudit_token` | Bearer-Token von mcp.flowaudit.de (aus der Claude-Code-Konfiguration) |
| GitHub-Kachel | `/etc/cockpit/env` → `GITHUB_TOKEN` | Token des gh-CLI (breite Scopes – besser durch ein fein granuliertes Read-only-Token ersetzen) |
| Kira-Memory | keine Ablage nötig | Schlüssel wird per SSH auf dem NUC aus `audit_designer/.env` gelesen |

Sonden mit Anmeldung: `{"login_url": "…/api/auth/login", "user_secret": "…", "password_secret": "…"}`
statt `secret_key`; bei HTTP 401 wird einmal neu angemeldet.

`kira_cloudflared` (Compose-Projekt `deploy` in kiraclaw, bewusst gestoppt) steht in der
Ausblendliste, damit die Wand keinen Dauer-Alarm zeigt.
