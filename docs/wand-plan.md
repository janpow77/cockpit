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

**v0.3.21:** KI-Nutzung als eigene Seite `/ki` (Halbkreis-Anzeigen je Limit mit Reset-Zeit,
Tokens je Tag, Modelle heute, Auslastung 7 Tage); Kopfzeile ohne Zählerzeile, dafür Link
„KI-Nutzung · Claude n %“. **Sitzungen:** Fenster aufklappen zeigt die letzten 40
Terminalzeilen (`tmux capture-pane`), darunter „Arbeitspaket“ – Text wird per
`tmux send-keys -l` in das Fenster getippt und mit Enter abgeschickt (Bestätigung durch
zweiten Klick, Audit-Eintrag `wall.tmux_senden`). Ziel-Form `sitzung:fenster`, Text ≤ 2000
Zeichen; Self-Hosts über Loopback-SSH. KI-Sonde nutzt denselben Loopback (die Dateien
liegen beim Nutzer, nicht im Container).

## 17. Aufträge – Kanban für Agentenläufe (v0.4.0, 28.08.2026)

Seite `/kanban` („Aufträge“ in der Seitenleiste, Link in der Wand-Kopfzeile). Jede Karte ist
ein Auftrag: Titel, Auftragstext, Projektverzeichnis auf einem Host (aus der Werkstatt),
**Agent** (Claude Code · Codex · Gemini), Profil, Priorität 1–5, Zeitfenster
(sofort · nachts 22–7 · nach Wochen-Reset). Spalten Eingang → Geplant → Läuft → Rückfrage
→ Fertig; Eingang↔Geplant per Drag & Drop. Detailpanel mit Ergebnis, Kosten/Tokens, Branch,
Diff-Link (GitHub compare) und Live-Protokoll; „Nachfrage“ setzt die Sitzung fort
(`--resume` / `codex exec resume` / `gemini -r`).

**Lauf:** Der Runner (`services/auftrag_runner.py`, alle 20 s) legt auf dem Host einen
Git-Worktree `<projekt>/.cockpit-auftraege/wt-<id>` mit Branch `auftrag/<id>` an (Verzeichnis
in `.git/info/exclude`) und startet dort den Agenten per `nohup` mit JSON-Protokoll
(`lauf.jsonl`, `stderr.txt`, `done.txt`, `pid.txt`). Befehle (`services/auftraege.py`):
Claude `claude -p "$(cat auftrag.txt)" <Profil> --output-format stream-json --verbose
--max-turns 80` (ohne `--bare`: läuft über die Max-Anmeldung, zählt aufs 5-Stunden-Fenster);
Codex `codex exec --json -s read-only|workspace-write [--approve-for-me]
--skip-git-repo-check`; Gemini `gemini -p … -o stream-json --approval-mode
default|auto_edit|yolo --skip-trust`. Programme absolut (`agent_bins`, weil `bash -lc`
über SSH `~/bin`/`~/.npm-global/bin` nicht kennt). Profile: `lesen` (nur Lesen, git/gh/rg,
graphify-MCP), `bearbeiten` (acceptEdits), `bearbeiten_tests` (+ npm/pytest/ruff/git commit),
`voll` (Classifier). Nie `--dangerously-skip-permissions`. Am Ende: Commit auf dem Branch,
Ergebnis/Kosten/Session aus dem letzten `result`-Ereignis, Rückfrage-Erkennung (Frage am
Schluss), Push per Telegram (fertig/Rückfrage/Fehler).

**Kontingent:** `parallel_max` aus der KI-Nutzung – Basis `auftrag_parallel` (3); ≥ 60 %
5-Stunden-Fenster → Basis−1, ≥ 85 % → 1, ≥ 95 % oder Woche ≥ 98 % → 0 (Pause mit Grund);
Gemini nur ein Lauf gleichzeitig. Geplante Aufträge starten nach Priorität/Reihenfolge, sobald
Kapazität und Zeitfenster passen.

**Vorlagen** (`services/auftrag_vorlagen.py`, 22 Stück, `{projekt}` wird ersetzt): Repo
prüfen, Oberfläche verbessern, Tests ergänzen, Sicherheits-Audit, Doku, Abhängigkeiten,
Performance, Fehler beheben, Sprache/Umlaute, **Vorschläge einholen**, PRs prüfen, Issues
sichten, Aufräumen/entflechten, Barrierefreiheit, Fehlerbehandlung/Logging, TODO/FIXME,
CI/flackernde Tests, Release vorbereiten, Datenschutz (DSGVO), Container härten, API-Doku,
Migrationen prüfen. Eigene Vorlagen über Einstellung `auftrag_vorlagen` (gleiche id ersetzt).
Quellen der Recherche: wshobson/commands, qdhenry/Claude-Command-Suite, awesome-copilot.

**Vorschläge (automatisch):** Vorlage „Vorschläge einholen“ liest Git-Verlauf, GitHub
(`gh`: Issues, PRs, CI, Dependabot), die graphify-Analyse von flow-agent
(`graphify-out/<Datum>/GRAPH_REPORT.md`, MCP auf 127.0.0.1:8765) und den Code und endet mit
einem JSON-Block; der Runner legt daraus Karten „Vorschlag: …“ in den Eingang (Dubletten
nach Titel je Projekt vermieden, Profil/Priorität aus dem Vorschlag). Wöchentlich
automatisch je aktivem Werkstatt-Projekt (Einstellung `vorschlaege`: aktiv, wochentag 6 =
Sonntag, stunde 1, agent; Zeitfenster nachts) oder auf Abruf über „Vorschläge einholen“
(`POST /admin/api/auftraege/vorschlaege`).

**Prüfstand 28.08.:** Probeläufe im Scratch-Repo – Claude (`lesen`, 2 Turns, Ergebnis/
Session/Kosten geparst), Codex (`thread.started`/`item.completed`/`turn.completed` wie im
Parser). Gemini CLI 0.46 auf dem NUC: `IneligibleTierError` – Code Assist für Einzelnutzer
wird vom CLI nicht mehr bedient; Abhilfe: API-Schlüssel in `~/.gemini/.env` oder
Antigravity-Anmeldung. Zwei Startbefehl-Fehler behoben: `&` löste die ganze `&&`-Kette in
den Hintergrund (jetzt Untershell), neues git legt `.git/info` nicht an (jetzt `mkdir -p`).

**v0.4.2 – Vorgehen je Auftrag und Freigabe:** Feld `modus` – **bericht** (nur analysieren
und einen Plan vorschlagen, läuft immer lesend), **plan_freigabe** (Vorgabe: der Agent
erstellt zuerst einen Plan, die Karte landet mit Status `freigabe` in „Rückfrage /
Freigabe“; „Umsetzen“ (`POST /{id}/umsetzen`, optionaler Hinweis) setzt dieselbe Sitzung mit
dem Schreibprofil der Karte fort; „Nur Bericht behalten“ → fertig), **umsetzen** (direkt).
Das Profil gilt nur für die Umsetzung (`effektives_profil`); Plan-/Berichtsphase bekommt
den Zusatz aus `PLAN_SUFFIX`, die Umsetzung den Text `umsetzungstext()`. Vorschlagsläufe
laufen als `bericht`. Migration 005 (`modus`, `freigegeben`).

**Vorlagen (31):** zusätzlich Standardaufgaben – Icons vereinheitlichen, Übersetzen/Sprache,
Farben/Abstände/Typografie (Design-Tokens), Leer-/Lade-/Fehlerzustände, Tabellen (Sortierung,
Filter, XLSX-Export, DD.MM.JJJJ), Formulare/Validierung, Mobile Ansicht, Benennung/Glossar,
Datenqualität. Jede Vorlage bringt ihren Modus mit (Audits → bericht, Änderungen →
plan_freigabe).

**Gemini/Antigravity:** Seit 18.06.2026 bedient die Gemini CLI keine Einzelkonten mehr
(Google AI Pro/Ultra/Free → `IneligibleTierError`); das Abo läuft nur noch über Antigravity
(IDE `antigravity` 1.107 ist auf dem NUC, die CLI `agy` nicht). Ein Gemini-API-Schlüssel
wird dagegen nach Tokens abgerechnet (AI Studio, Free-Tier mit Datennutzung). Der Cockpit-
Agent „Gemini“ unterstützt beides: `agent_bins.gemini` auf `~/.local/bin/agy` zeigen →
`agy -p … --output-format stream-json --sandbox [--dangerously-skip-permissions für
Schreibprofile, da der Druckmodus keine Regel-Freigaben kennt]`, Fortsetzung
`--conversation <id>`; sonst klassisch `gemini -p … -o stream-json`. agy-Pfad ist
vorbereitet, aber ungetestet (Installation `curl -fsSL https://antigravity.google/cli/install.sh | bash`
und Google-Anmeldung sind Nutzeraktionen).

**flow-agent als Datenquelle (v0.4.4):** `services/flow_agent.py` liest mit dem Lese-
Schlüssel (Vault `flow_agent_read_key`, Einstellung `flow_agent` mit `url`, `secret_key`,
`hosts` = flow-agent-Hostname → Cockpit-Host, z. B. `janpow-NUC15JNLU7X4 → nuc`,
`cockpit-nbg1-1 → ccx23`, `evo2 → evo`, `MacBook-Air.local → macbook`) das Projektinventar
`/api/v1/projects` (Git-Stand, dirty/ahead/behind, Technologien je Host – 110 Projekte auf
5 Hosts) und `/api/v1/graphify/status`. Die Projektliste des Kanbans zeigt damit alle Repos
aller Hosts (Quelle, Branch, uncommittete Änderungen, graphify-Stand); Hosts ohne SSH-Zugang
des Cockpits sind als nicht ausführbar markiert. Vorschlagsläufe bekommen einen Kontextblock
„Stand laut flow-agent“ (Git-Zustand, Technologien, graphify-Alter, Hinweise) an den
Auftragstext gehängt. 5 min Cache, Fehler → leere Ergebnisse.

**Codex-Sandbox (v0.4.5):** Codex' bubblewrap-Sandbox scheitert auf dem NUC
(`bwrap: loopback: Failed RTM_NEWADDR: Operation not permitted`, auch für `read-only`) –
der Planlauf lieferte den Plan ohne Lesezugriff, die Umsetzung „nichts geändert“. Einstellung
`codex_sandbox` (Vorgabe `danger-full-access` = ohne Isolierung, wie in der `~/.codex/config.toml`
des Nutzers; `workspace-write` dort, wo bwrap läuft). Nie `--dangerously-bypass-approvals-and-sandbox`;
Schutz bleibt Worktree + Branch je Auftrag. Beim `exec resume` gehen Sandbox und Freigabe nur
als `-c sandbox_mode=… -c approval_policy=never` (keine `-s`/`--approve-for-me`-Flags).

**flow-agent-Kachel (v0.4.7):** `flow_agent.zustand()` fasst `/api/v1/health` (ohne Auth),
`/agents`, `/freshness`, `/notifications/summary` und `/operations/status` zusammen (Cache
60–120 s): Control Plane + Version, Hosts mit Status/Alter/Projekte/Container/GPU, tmux-Zustand
und fehlende Werkzeuge, Frische-Zähler mit nicht-grünen Befunden (max. 8), offene/
fehlgeschlagene Aktionen. Handlungsbedarf: Host offline/unhealthy → kritisch; Check unhealthy,
fehlgeschlagene Aktionen, Control Plane weg → Warnung; wartende Aktionen → Info. Befund vom
28.08.: „degraded“ auf 4 Hosts kommt aus tmux-Bewertung und fehlenden Werkzeugen (NUC: restic,
uv, caddy; EVO: restic, rclone, nvidia-smi, node, npm, gh; Hetzner: nvidia-smi, uv; janpow-ai:
uv, caddy), einziger nicht-grüner Check „Wissensbasis-Harvest“ (Endpunkt verlangt Anmeldung,
HTTP 401); die Host-Agenten liefern kein graphify-Feld (`/graphify/status` leer).

**Gemini über das Abo mit agy (v0.4.8, 28.08.2026):** Antigravity CLI 1.1.22 auf dem NUC
installiert (`~/.local/bin/agy`, Anmeldung per Google-OAuth in einer tmux-Sitzung, Code aus
dem Browser eingefügt). Headless: `agy -p … --output-format stream-json --mode plan|accept-edits`,
Fortsetzung `--conversation <id>`; Ereignisse `event: init` (conversation_id, permission_mode),
`step_update` (step_type tool mit tool_name/tool_info.parameters.CommandLine, agent_response mit
usage), `result` (status SUCCESS|CANCELED, response, usage input/output/thinking/cache_read).
Im Druckmodus kann agy keine Freigaben erfragen – ohne Regeln endet der Lauf mit
`CANCELED` und leerer Antwort („no output produced — a tool required the … permission“).
Deshalb `~/.gemini/antigravity-cli/settings.json` → `permissions.allow` mit 27 Regeln:
Lesen (`read_file(/)`, `view_file(/)`, `list_dir(/)`, `grep_search(/)`, `find_by_name(/)`),
Kommandos (`command(git)`, `command(rg)`, `command(cat)`, `command(sed)`, …,
`command(gh (pr|issue|run|api|repo))`, `command(npm run (build|lint|test|type-check|format:check))`,
`command(pytest)`, `command(ruff)`). `--sandbox` scheitert auf dem NUC („connecting to
sandbox server … connection reset“) und bleibt weg. `agent_bins.gemini` zeigt auf beiden
Instanzen auf agy. Gemini CLI 0.46 bleibt installiert, wird aber nicht mehr benutzt.

**v0.4.9:** Erster Gemini-Lauf im Worktree endete mit `CANCELED` – agy setzte Kommandos
außerhalb der Allow-Regeln ab (`pgrep`, `ps` …); im Druckmodus bricht dann der ganze Lauf ab.
Daher agy-Profile mit `--dangerously-skip-permissions` (wie Codex ohne Sandbox auf dem NUC),
der Ausführungsmodus (`--mode plan` bzw. `accept-edits`) begrenzt weiterhin Dateiänderungen;
Schutz bleibt Worktree + Branch. Die Allow-Regeln in `settings.json` bleiben für interaktive
agy-Nutzung erhalten.

**v0.4.10:** Gemini-Testlauf: agy schrieb `calc.py`/`test_calc.py` in sein eigenes
Scratch-Verzeichnis (`~/.gemini/antigravity-cli/scratch/`) statt in den Worktree (Branch blieb
leer). Behoben mit `--add-dir <worktree>` und einer ersten Prompt-Zeile „Arbeitsverzeichnis
(Git-Worktree, Branch …): <pfad> – alle Änderungen ausschließlich dort“ für alle Agenten beim
Erststart.

**Instanz janpow-ai (28.08.2026, v0.4.10):** `http://100.114.73.106:7843` (Tailscale-only,
Host-Netz), Admin-Passwort in `/home/janpow/cockpit-instanz/.admin_pw` auf janpow-ai, Vault-
Secrets vom Hetzner gespiegelt, `AI_ROUTER_URL=http://100.102.132.11:7849` (Router des NUC über
Tailscale), `agent_bins.gemini` → agy. Ablauf: Image `docker save | ssh janpow-ai docker load`,
`instanz_deploy.sh` per scp auf den Host und **dort** ausführen (das Skript arbeitet immer lokal –
ein Aufruf auf dem NUC mit `janpow-ai` als Argument rollt auf den NUC aus). SSH von janpow-ai zu
NUC (`janpow@`) und Hetzner (`deploy@`) funktioniert. Desktop-Verknüpfung
`~/Schreibtisch/Cockpit.desktop` (xdg-open auf die Wand).

**Prüfstand 28.08. (echte Aufgabe, v0.4.11–0.4.13):** Auftrag „README: Abschnitt Aufträge
(Kanban) ergänzen“ auf dem Cockpit-Repo (Claude, Plan mit Freigabe): Plan in 75 s, Umsetzung
in 129 s, Commit `c233939` auf `auftrag/a_323013db73` (25 Zeilen, sachlich, Umlaute korrekt).
Befund: der `post-commit`-Hook des Nutzers (graphify) erzeugte im Worktree eine neue
`ARCHITEKTUR.md`, die der Abschluss-Commit mitnahm → `abschluss_befehl` setzt
`HOOK_ARTEFAKTE` (ARCHITEKTUR.md, ARCHITECTURE.md, graphify-out) vor dem Commit zurück,
schließt sie aus und committet mit `core.hooksPath=/dev/null`; „Letzte Zeile“ zeigt nur bei
eigenem Commit den Diff-Umfang (sonst „keine Änderungen im Branch“ statt des Stats des
Vorgänger-Commits). Frontend-Test per Playwright (Token in `localStorage`
`cockpit_admin_token`): Formular → „Sofort planen“ → Läuft → Fertig, Detailpanel mit Bericht
(Codex, „Nur berichten“, vier Umlaut-Fundstellen in der README). Beobachtet: beim Spaltenwechsel
erscheint die Karte für einen Poll-Zyklus in zwei Spalten (Anzeige, kein Datenfehler).

**v0.4.12:** „KI-Nutzung“ ist kein eigener Tab mehr – Kopfzeilen-Link der Wand und Sidebar-
Eintrag entfernt (`/ki` leitet auf `/kanban`), die Anzeige lebt als einklappbarer Bereich
(`components/kanban/KiNutzungPanel.vue`) unter der Kapazitätsleiste des Kanbans; Zustand in
`localStorage`.

**v0.4.13 – Wording:** In allen sichtbaren Texten „LLM“ statt „KI“ (LLM-Konsole, LLM-Nutzung,
LLM-Aufträge, LLM-Host); Projektname „KI-Pilotprogramm“ bleibt. Bezeichner, Routen (`/chat`,
`/ki`) und Dateinamen unverändert. Außerdem: Karte beim Spaltenwechsel nicht mehr doppelt
(Dedup nach id, keine Leave-Animation über Spalten hinweg).
Halbkreis-Anzeigen der LLM-Nutzung: der Wertbogen (`bogen()`) nutzte ab 50 % das
Large-Arc-Flag – der Bogen überspannt aber nie mehr als 180°, Flag daher immer 0 (v0.4.13).

**v0.4.15 – Agenten-Hosts:** Ein Auftrag auf dem Hetzner-Host (`ccx23`,
`/home/deploy/Projekte/regulierung`, Gemini) scheiterte mit `agy: No such file or directory` –
die Agenten (claude, codex, agy) sind nur auf dem NUC installiert und angemeldet. Einstellung
`agent_hosts` (Vorgabe `["nuc"]`): Projekte auf anderen Hosts erscheinen im Kanban mit Grund
„keine Agenten auf diesem Host“ und sind nicht wählbar; Anlegen/Start/Vorschläge liefern 422
mit Hinweis auf die Kopie des Projekts auf dem Agenten-Host; der Runner startet solche
geplanten Aufträge nicht, sondern setzt sie mit klarem Fehlertext auf „Fehler“; wöchentliche
Vorschlagsläufe nur für Agenten-Hosts. Wer Agenten auf einem weiteren Host anmeldet, trägt ihn
in `agent_hosts` ein (und passt ggf. `agent_bins` an).

**v0.4.16 – Push ohne Flattern:** Der Nutzer bekam per Telegram ständig „… antwortet nicht
(ConnectTimeout)“ mit Entwarnung kurz darauf. Zwei Ursachen: (1) alle drei Instanzen pushten in
denselben Chat – die janpow-ai-Instanz sieht `pilot/pdf/zvg/mcp.flowaudit.de` mit Timeouts
(5–6 s Antwortzeiten aus ihrem Netz); (2) jeder Wand-Lauf meldete sofort. Abhilfe: Push nur noch
auf dem Hetzner-Cockpit (`push.aktiv=false` auf NUC und janpow-ai, `push.instanz` benannt) und
`push.bestaetigen()`: ein Alarm wird erst nach `bestaetigung_laeufe` (Vorgabe 2 ≈ 3 min)
aufeinanderfolgenden Läufen gemeldet, die Entwarnung erst nach ebenso vielen Läufen ohne den
Alarm; Zähler in Setting `alerts_zaehler`, gemeldete Schlüssel weiter in `alerts_state`.
Ruhezeit: zurückgehaltene Warnungen gelten als bestätigt und gehen morgens gesammelt raus.

## 18. Ausbaukonzept, Phase 1 und 3 (v0.4.17, 28.08.2026)

Konzept: https://claude.ai/code/artifact/3ba85022-812c-45fc-91b1-6b4065dc9522 (sechs
Arbeitspakete; entschieden: immer PR, das Cockpit prüft, mergt aber nie).

**Phase 1 – robuster Runner:** `stand_befehl` meldet zusätzlich `PID_LEBT` und `LOG_ALTER`;
ohne Ende-Marke und ohne lebenden Prozess (Neustart des NUC) oder nach
`auftrag_max_dauer_min` (90) gilt der Lauf als **unterbrochen** (Sitzungs-ID aus dem Protokoll
gesichert, Worktree bleibt). „Fortsetzen“ (`POST /{id}/fortsetzen`) setzt die Sitzung mit
`UNTERBROCHEN_PROMPT` fort (git status/diff prüfen, dort weitermachen), ohne Sitzung neuer Lauf
im bestehenden Worktree. Zughöchstzahl je Profil (`MAX_TURNS_PROFIL`: lesen 40, bearbeiten 120,
bearbeiten_tests/voll 150), agy `--print-timeout 45m`. Runner-Schalter
(`POST /auftraege/runner {angehalten}`, Setting `runner_angehalten`): geplante Aufträge starten
nicht, laufende laufen weiter – vor dem NUC-Aus. Aufräumen: `POST /{id}/aufraeumen`
(Worktree, optional Branch) und automatisch nach `auftrag_aufraeumen_tage` (14) für
fertig/fehler/abgebrochen.

**Phase 3 – Qualitätstor und PR:** Nach jeder Umsetzung (nicht nach Bericht/Plan) führt
`pruefen()` die Prüfbefehle im Worktree aus – aus `.cockpit.yaml` (`basis`, `pruefung: [...]`,
`merge: pr`) oder per Erkennung (pyproject → ruff + pytest, backend/requirements.txt →
pytest im backend, frontend/package.json → type-check + build), je Befehl 15 min Zeitlimit,
Ergebnis als JSON in `pruefung` und `pruefung_ok` (Abzeichen auf der Karte). „PR erstellen“
(`POST /{id}/pr`): Branch pushen, `gh pr create --base <basis>` mit Ergebnis und Prüfprotokoll
als Beschreibung; `pr_url` an der Karte, GitHub-Checks per `gh pr checks` alle ~100 s als
Kurzstand `pr_checks`. Das Cockpit mergt nie. `.cockpit.yaml` liegt im Cockpit-Repo und
(uncommittet) im HPP-Repo. `act` (GitHub Actions lokal) ist auf dem NUC nicht installiert –
optionaler Zusatz für Repos mit Workflows. Migration 006.
