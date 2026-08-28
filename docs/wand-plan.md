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

## 11. Anmeldung, Erreichbarkeit, Stand v0.3.4 (27.08.2026)

- **Anmeldung** über die Seite `/admin/login` mit Benutzername und Passwort. Benutzername
  aus `COCKPIT_ADMIN_USER` (Vorgabe `admin`), Passwort aus `COCKPIT_ADMIN_PASSWORD`
  (`/etc/cockpit/env`). Skripte ohne Benutzername laufen weiter (Vorgabe `admin`).
  Das Cockpit bleibt bewusst Tailscale-only (Docker-Socket, Vault) – eine öffentliche
  Adresse bräuchte Cloudflare Access davor.
- **Alle Anwendungen erreichbar:** Projekte mit öffentlicher Adresse verlinken diese;
  Projekte ohne Adresse verlinken ihre veröffentlichten Ports über die Tailscale-IP des
  Hosts (`intern_urls()`, nur 0.0.0.0-/Tailscale-Bindungen, keine 127.0.0.1).
- **Alle Repositories:** Die GitHub-Kachel zeigt sämtliche Repositories nach Aktivität
  (ältere als 90 Tage abgeblendet), Werkstatt-Zeilen verlinken das passende Repository.
- **MCP flowaudit:** mcp.flowaudit.de wird vom NUC bedient (Container
  `audit_designer_mcp_memory` hinter `audit_designer_cloudflared`), nicht vom Hetzner-
  Replikat. Der Service-Token des Cockpits ist als SHA-256 in
  `MCP_SERVICE_TOKEN_SHA256S` der `audit_designer/.env` auf dem NUC eingetragen (und
  zusätzlich in `/etc/checklist/env` auf dem Hetzner); der Token selbst liegt im Vault
  (`mcp_flowaudit_token`).

## 12. Kira-RAG in der KI-Konsole (v0.3.5)

Die Konsole kann vor jeder Antwort Kira befragen. Umschalter „Kira“ im Kopf: **Aus ·
Gedächtnis · Wissen · Beides** (Vorgabe Beides), dazu ein optionales Projektfilter-Feld.
Ablauf je Anfrage (`routes/chat.py` + `services/rag.py`):

1. Die letzte Nutzerfrage (max. 500 Zeichen) wird gesucht – **Gedächtnis** über das
   MCP-Werkzeug `memory_search` (mcp.flowaudit.de, Service-Token aus dem Vault), Rückfall
   `POST /api/memory/search` per SSH-`curl` auf dem NUC; **Wissensbasis** über
   `knowledge_search` (nur MCP). Beide Suchen laufen parallel.
2. Treffer werden normalisiert (Protokoll-Kategorien und private Projekte bleiben weg),
   gekürzt (Gedächtnis 1 200, Wissen 1 000 Zeichen) und als nummerierter Kontextblock an
   den Systemprompt gehängt; das Modell soll mit [1], [2] … zitieren und sagen, wenn der
   Kontext nichts hergibt.
3. Als erster SSE-Chunk gehen `sources` (für die Anzeige) und ggf. `rag_note` (welcher Weg
   nicht ging) an die Konsole, dann streamen die Tokens wie bisher.

Parameter der Konsole: Modell (Whitelist), Temperatur 0–1,5, Systemprompt (Vorgabe in
den Einstellungen), Kira-Modus + Projekt, Kontextfenster `chat_num_ctx` (Vorgabe 12 288
Tokens, nur bei aktivem RAG gesetzt). Kein Verlauf auf dem Server; der Browser hält das
Gespräch in `localStorage`.

**Denkmodus (v0.3.6):** Die Qwen-Modelle „denken“ vor der Antwort (Ollama `think`). Mit
Denkmodus brauchte eine Drei-Satz-Antwort mit RAG 2 742 Tokens und 241 s, ohne 62 Tokens
und 5 s. Die Konsole schickt deshalb `think: false` (Einstellung „Denkmodus des Modells“,
Vorgabe aus). Wer ausdrücklich lange Herleitungen will, schaltet ihn dort ein.

**MCP-Upstreams:** mcp.flowaudit.de wird über den Cloudflare-Tunnel von zwei Replikaten
bedient (NUC `audit_designer_mcp_memory` und Hetzner `checklist-mcp-memory`); der
Service-Token-Hash muss daher in BEIDEN Umgebungen stehen (`audit_designer/.env` auf dem
NUC, `/etc/checklist/env` auf dem Hetzner), sonst antwortet jede zweite Anfrage mit 401.

## 13. Weitere Instanzen: NUC und janpow-ai (v0.3.7)

Dieselbe Wand kann auf jedem Linux-Host der Landschaft laufen – als Zweitzugang, wenn der
Hetzner nicht erreichbar ist, oder als lokale Wand mit dem jeweiligen Host in der Mitte.

```bash
# 1. Image auf den Host bringen (vom NUC aus; auf dem NUC selbst entfaellt das)
docker save cockpit:v0.3.7 | gzip -1 | ssh janpow@100.114.73.106 'gunzip | docker load'
# 2. Instanz anlegen (auf dem Host): Self-Host-Name, Image-Tag, optional Verzeichnis
AI_ROUTER_URL=http://127.0.0.1:7849 scripts/instanz_deploy.sh nuc v0.3.7        # auf dem NUC
scripts/instanz_deploy.sh janpow-ai v0.3.7                                        # auf janpow-ai
# 3. Vault-Secrets vom Hetzner abgleichen (vom NUC aus, ueber SSH – nichts auf Platte)
scripts/instanz_secrets_sync.sh http://100.102.132.11:7843 ~/cockpit-instanz/.admin_pw
```

Was `instanz_deploy.sh` anlegt (`~/cockpit-instanz/`): `env` mit Admin-Passwort und Vault-
Schlüssel (einmalig, Passwort zusätzlich in `.admin_pw`), `config.yaml` mit allen fünf Hosts
(Self-Host markiert), `compose.yaml` im **Host-Netz** (damit Memory-API und ai-router-Hub
auf 127.0.0.1 erreichbar sind), gebunden **nur an die Tailscale-IP** des Hosts. Mounts wie
auf dem Hetzner: Docker-Socket, `~/.ssh/id_ed25519` als Cockpit-Schlüssel, `~/Projekte`
(Werkstatt + Kira-`.env`) und ein Sicherungsverzeichnis, alles nur lesend.

Voraussetzungen je Host: Docker mit Compose-Plugin, Tailscale, der Host-Schlüssel
`~/.ssh/id_ed25519` ist auf den anderen Hosts eingetragen (Hetzner `deploy`, EVO, MacBook
`janriener`, janpow-ai). `janpow-ai` (100.114.73.106) war am 27.08.2026 offline – Deploy
vorbereitet, Ausführung sobald der Rechner läuft.

**Demo-Start (v0.3.10):** HPP baut die Demo seit Commit `regulierung` „Demo-Aufbau als
Hintergrundauftrag“ asynchron: `POST /demo/aufbauen` antwortet 202, `GET /demo` liefert
`aufbau {laeuft, beendet, fehler, ergebnis}`, ein zweiter Start bekommt 409. Grund: Der
Aufbau dauert 1–3 Minuten, der Cloudflare-Tunnel kappt Antworten nach 100 s (HTTP 524),
und zwei parallele Aufbauten liefen in einen DB-Deadlock. Die Wand startet, zeigt die
Sekunden auf der Hero-Karte, fragt alle 5 s nach und öffnet danach das reguläre Portal
(`/kraftstoff/vollzug`) **im selben Fenster** – kein Pop-up, keine eigene Demo-Seite.

## 14. Prüfstand 27.08.2026 (Smoketests, Codex-Review)

- **HPP-Abnahmetest** `scripts/hpp_acceptance_smoke.sh` (regulierung): 11/11 bestanden
  (pytest, Frontend-Build, Container, API, SPA-Routen, UI-Guards).
- **Cockpit** `scripts/cockpit_smoke.sh <url> <pw-datei>` (von Codex geschrieben, nur lesend):
  Login, Health, Overview-Pflichtfelder, Dienste, Modelle, MCP-Werkzeuge, SSE-Chat, Demo-Start
  (`neu=false` → übersprungen), Konfiguration. Gegen NUC- und Hetzner-Instanz grün.
- **Browser** (Playwright): Login-Formular, Wand (Hero-Kennzahlen, Knöpfe, Alarme, Laufband),
  Konsole (Modelle, Kira-Umschalter), MCP-Seite; HPP-Prod als `claude-smoke`: Demo-Seite
  (fünf Fälle), Vorgänge mit DEMO-Kennzeichen, Akte.
- **Codex-Review** (Dateien overview/chat/rag/wall_extras/ai_router_client/auth) – umgesetzt:
  `env_key` nur als Variablenname (Shell-Injection über Konfiguration), Sonden und
  Host-Abfragen kapseln (kein 500 mehr), Demo-Antworten validiert (kein `ok` bei leerer
  Fallliste), Router-Antworten robust, Modellliste außerhalb des Eventloops, Logout widerruft
  die tatsächliche Sitzung, TLS-Cache je Host+Port, Ausblendliste auf den ganzen Text,
  Quellen im Prompt als Daten gekennzeichnet, Tunnel nur bei laufendem Container,
  Kennzahlen-Ausfall des Self-Hosts meldet sich.
- **Offen (bewusst, Admin-Konfiguration ist Tailscale-only):** Allowlist für konfigurierbare
  URLs (Sonden, Demo, MCP) gegen SSRF/Secret-Abfluss nach Admin-Übernahme; Rate-Limit am
  Login; Cache-Schlüssel mit Konfigurationshash; IPv6-Adressen in internen Links.

**Relevanz (v0.3.14):** Ohne Schwellen verwässerte die Wissensbasis fachfremde Fragen
(Drucksachen und Jahresberichte mit Score ~0,57 zu einer Frage nach Hetzner-Diensten).
Jetzt: Gedächtnis ≥ 0,32, Wissensbasis ≥ 0,62 im Modus „Beides“ (≥ 0,50 bei „Wissen“),
Dubletten je Chunk entfernt, Suchanfrage bei kurzen Rückfragen um die vorige Frage ergänzt,
Systemprompt mit Glossar (HPP, KPAnG, MTS-K, VerwK, TER/RER). Jede Anfrage schreibt eine
Protokollzeile („Konsole: modell=… rag=… quellen=… suche=… ms“) ins Container-Log.

## 15. Alltagstauglichkeit (v0.3.15, 28.08.2026)

| Baustein | Was er tut | Wo |
| --- | --- | --- |
| **Hintergrundlauf** | ermittelt den Stand alle 90 s (`COCKPIT_WALL_INTERVAL`), die API liefert ihn sofort aus (`?frisch=1` erzwingt Neuermittlung) | `services/wall_loop.py` |
| **Push-Alarme** | neue Punkte ab `min_level` (warn) per Telegram über den Kira-Bot, Entwarnung bei Wegfall, Ruhezeit 22–07 Uhr nur Kritisches; Vergleich gegen `alerts_state` (kein Doppelalarm nach Neustart); Test-Knopf in den Einstellungen | `services/push.py`, Vault `telegram_bot_token`/`telegram_chat_id`, Einstellung `push` |
| **Verlauf** | Kennzahlen je Lauf in `cockpit_wall_samples` (Host-Last/RAM/Platte/GPU, Hero-Kennzahlen, Alarmzahlen, Dienst-Antwortzeiten, Kira-Bestand), 30 Tage; Verlaufslinien unter den Hero-Zahlen und bei den Hosts; `GET /admin/api/overview/verlauf?hours=24&keys=…` | `services/verlauf.py` |
| **tmux-Sitzungen** | Kachel „Sitzungen“: Sitzung, Fenster mit laufendem Programm, verbunden/seit; Self-Hosts per Loopback-SSH (Cockpit-Schlüssel für `deploy@ccx23` bzw. `janpow@nuc` eingetragen) | Host-Sonde `host_stats._CMD` |
| **Werkstatt** | nur Repos mit Commit oder Pause in den letzten 14 Tagen (`werkstatt_aktiv_tage`), ältere aufklappbar, „Nächster Schritt“ der jüngsten Pause oben | `wall_extras.parse_werkstatt` |
| **Konsole** | Wissensbasis bei „Beides“ nur für fachliche Fragen (Regex), Antwortlänge `chat_max_tokens` (900), knapperer Systemprompt; „Ins Gedächtnis“ schreibt Frage+Antwort als Kira-Eintrag (`POST /admin/api/chat/merken` → `memory_add` über MCP, Rückfall Memory-API) | `routes/chat.py` |
| **Handy** | `/kompakt`: Handlungsbedarf, HPP-Kennzahlen, Dienste, Hosts, 60-s-Takt | `views/KompaktView.vue` |
| **Login** | 5 Fehlversuche je IP → 60 s Sperre (429); Token-Antworten `Cache-Control: no-store` | `routes/auth.py` |
| **Deploy** | `scripts/hetzner_deploy.sh [tag]`: bauen, laden, starten, aufräumen, Smoketest | |

**Sicherheitslage (Bewertung 28.08.2026):** Beide Instanzen hängen ausschließlich an
Tailscale-Adressen – aus dem Internet sind sie nicht erreichbar, jede Verbindung ist
über WireGuard authentifiziert. Innen: ein Admin-Konto mit zufälligem Passwort, jetzt
mit Sperre nach Fehlversuchen; Sitzungstoken mit Ablauf; Vault mit Fernet verschlüsselt;
Secrets werden nie ausgeliefert. Wer das Passwort hat, hat aber den Docker-Socket des
Hosts (root-gleich) und den Vault – das Passwort ist der eine Schlüssel. Offen bleibt die
Allowlist für konfigurierbare Ziel-URLs (Sonden, Demo, MCP) und ein Zweitfaktor; beides
wird Pflicht, sobald das Cockpit je hinter einer öffentlichen Adresse hinge (dann nur mit
Cloudflare Access davor).

**Loopback-SSH auf dem Hetzner (v0.3.16):** Der Cockpit-Container hängt im Bridge-Netz
`cockpit` (172.18.0.0/16); die Tailscale-IP des eigenen Hosts ist von dort nicht
erreichbar, und ufw ließ 22/tcp aus dem Docker-Netz nicht durch. Lösung: ufw-Regel
`allow from 172.18.0.0/16 to any port 22 proto tcp` (Kommentar docker-cockpit-to-ssh) und
`COCKPIT_SELF_SSH_HOST=host.docker.internal` mit `extra_hosts: host-gateway` in der
compose.yaml; der Cockpit-Schlüssel ist bei `deploy` eingetragen. Verlaufstabelle kommt
per Migration `003_wall_samples.sql` (Tabellen entstehen nur aus `src/cockpit/migrations`).

**Statuskarte (v0.3.17):** Push-Nachrichten kommen als Bild (`services/statuskarte.py`, Pillow,
DejaVu im Image): Kopf mit Instanz und Zeit, je Punkt eine Zeile mit Farbbalken, „entwarnt“
grün, Verlauf 24 h der betroffenen Kennzahlen (Platte/RAM/Last je Host, Antwortzeit je
Dienst, sonst Alarmzahlen), Fußzeile mit Zusammenfassung und Wand-Adresse; Kurztext als
HTML-Caption. Ohne Bild (Pillow/Schrift fehlt, Telegram lehnt ab) geht reiner Text raus.

**Sonden-Fallstricke (v0.3.18/19):** Ein fehlender tmux-Server liefert Exit 1 – daher `|| true`;
auf macOS läuft die Sonde in zsh, das bei leeren Globs (`/sys/class/drm/card*`) den Befehl
abbricht – daher `setopt nonomatch` am Anfang und die GPU-Schleife nur bei vorhandenem
`/sys/class/drm`. Beides erzeugte sonst den Fehlalarm „Kennzahlen nicht abrufbar“.

## 16. KI-Nutzung (v0.3.20)

Kachel „KI-Nutzung“ mit drei Spalten – **Claude** (Claude Code, Max): Auslastung des
5-Stunden- und des 7-Tage-Fensters mit Reset-Zeit aus `api.anthropic.com/api/oauth/usage`
(Anmeldung aus `~/.claude/.credentials.json` des NUC, Token verlässt den Host nicht) und
Tokens je Tag/Modell aus `~/.claude/projects/*/*.jsonl`; **Codex** (ChatGPT): zuletzt
gemeldete `rate_limits` (Wochenfenster, Plan) und Tokenzähler aus `~/.codex/sessions`;
**Gemini**: keine lokalen Nutzungsdaten (ehrlich als „keine Daten“). Sonde
`services/ki_nutzung.py` läuft als Python-Skript auf dem Arbeitsplatz-Host (Einstellung
`ki_nutzung`), 5 min Cache. Alarm ab `warn_pct` (85 %) je Limit, kritisch ab 97 %;
Limit-Prozente und Tages-Tokens landen im Verlauf (`ki.claude.seven_day`, …). Für die
Abo-Konten gibt es keine offiziellen Nutzungs-APIs – die Werte kommen genau aus den
Quellen, die auch die Apps selbst anzeigen.
