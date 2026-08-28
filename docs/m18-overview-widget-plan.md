# M18 — System-Overview-Widget (vollständiger Umsetzungsplan)

> Stand: 2026-05-27 · Status: **PLAN (umsetzungsreif)** · gehört zu `sanierung-fahrplan.md` (Stufe 4 / M18).
> Voraussetzung erfüllt: M0 (Admin-DB-SoT-Export) + M11 (cockpit kennt alle Apps).
> Dieser Plan ist an den **realen cockpit-Code** (Stand Branch `feat/cockpit-deploy-und-konsistenz`) und die **ai-router-Admin-API** angedockt.

---

## 1. Leitprinzip

**Read-only „Single Pane of Glass".** Das Widget aggregiert Status aus den vorhandenen Quellen und **verlinkt** zum Handeln in die jeweiligen Admin-UIs. **KEIN eigener Konfigurator** — Schreib-/Config-Hoheit bleibt bei **cockpit** (Management) + **ai-router-Admin** (Registry/SoT, admin.db). Damit entsteht kein vierter, divergierender Config-Pfad (vgl. F0 im Konsistenz-Audit).

Einzige Schreib-Aktion, die das Widget anbietet, ist die **bereits existierende** `deploy_app`-Aktion (cockpit, M11) — als Deep-Link/Button, nicht neu gebaut.

---

## 2. Ist-Stand cockpit (was schon da ist — NICHT neu bauen)

| Baustein | Datei | liefert |
|---|---|---|
| Dashboard-Aggregat | `routes/dashboard.py` → `GET /admin/api/dashboard` | apps_total/healthy/down/unknown, hosts_total/online, Backups, Secrets, Repos, recent_audit |
| App-Status | `crud/apps.py` + `services/health_check.py:check_app` | `last_status` (healthy/down/degraded/unknown) je App, http-Probe gegen `healthcheck_url`, Container-Status |
| Host-Status | `services/health_check.py:check_host` + `services/tailscale.py` | online/offline/ssh-down/unreachable, Tailscale-Peer-Info, SSH-ping ms |
| App-/Host-Modell | `services/bootstrap.py` | `host, name, container_filter, compose_path, healthcheck_url` — inkl. `ccx23/llm-router` (Probe `http://100.99.159.80:7842/health`) |
| Deployments | `routes/deployments.py`, `services/docker_inspect.py:deploy_app` | letzte Deploys + `POST /admin/api/apps/{id}/deploy` |
| Traffic | `routes/traffic.py`, `services/traffic_collector.py` | Traffic-Daten (Basis für default-Traffic-Warnung) |
| Secret-Vault | `services/secret_vault.py`, `routes/secrets.py` | verschlüsselte Token-Ablage (→ ai-router-Admin-Token) |
| Frontend | `frontend/src/views/DashboardView.vue`, `stores/poll.ts` | bestehende Dashboard-Seite + Polling-Store |

**Fazit:** Hosts, Apps, Deployments, Traffic, Health, Secret-Vault existieren bereits. Die **Lücke** ist ausschließlich:
1. der **LLM-Router-Block** (Spokes/Routes/Quota/default-Traffic aus der ai-router-Admin-API) — es gibt noch keinen ai-router-Admin-Client in cockpit,
2. ein **vereinheitlichtes Overview-Aggregat** (ein Endpoint, der alles bündelt) + reichere Frontend-Seite,
3. **evo-x2 als cockpit-Host** (M11b) — fehlt bislang.

---

## 3. Datenquellen (alles read-only)

| Bereich | Quelle | Endpunkt / Mechanismus |
|---|---|---|
| Apps (Status/Health/letzter Deploy) | cockpit (DB) | `crud_apps` + `health_check.check_app` |
| Hosts (Tailscale/SSH, online) | cockpit | `health_check.check_host` + `tailscale.peer_status_by_ip()` |
| Deployments (letzte) | cockpit (DB) | `crud` deployments |
| **Spokes (online/offline, caps)** | **ai-router-Admin** | `GET {router}/admin/api/spokes` (Auth: Admin-PW) |
| **Routen** | **ai-router-Admin** | `GET {router}/admin/api/routes` |
| **App-Quota/Stats, default-Traffic** | **ai-router-Metrics** | `GET {router}/admin/api/metrics` |
| LLM-Spoke-Health (evo/nuc) | ai-router | `GET {router}/health` |
| Hosts-Ressourcen (Disk/RAM) optional | cockpit via SSH | `ssh_runner` (df/free), nur falls gewünscht |

`{router}` = zwei Instanzen:
- **NUC ai-router** `http://<nuc-tailscale>:7849`
- **CCX23 llm-router** `http://100.99.159.80:7842`

Beide haben dieselbe Admin-API; Auth via `LLM_ROUTER_ADMIN_PASSWORD` (NUC-PW liegt in `ai-router/.env`, CCX23-PW gesetzt). Token kommt in den **cockpit-Secret-Vault** (siehe §6).

---

## 4. Backend-Umsetzung

### 4.1 Neuer Service: `services/ai_router_client.py`
Schlanker read-only-Client für eine ai-router-Instanz.

```python
class AiRouterClient:
    def __init__(self, base_url: str, admin_password: str, timeout: float = 4.0): ...
    async def health(self) -> dict          # GET /health        → spokes-Health
    async def spokes(self) -> list[dict]     # GET /admin/api/spokes
    async def routes(self) -> list[dict]     # GET /admin/api/routes
    async def metrics(self) -> dict          # GET /admin/api/metrics
```
- Auth-Header/Session-Login je nach ai-router-Admin-Auth (PW → Session-Cookie oder Basic; an der real existierenden Admin-Auth ausrichten).
- **Fail-soft:** jeder Call fängt Timeout/Connection ab und liefert `{"reachable": False, "error": ...}` statt zu werfen — eine offline Router-Instanz darf das Overview nicht kippen (vgl. `ai_router_reachable_false_alarm`: passive Tracker meiden, aktiv pingen).
- Konfiguration der zwei Instanzen in `config.py` (`AI_ROUTERS = [{"name":"nuc","url":...},{"name":"ccx23","url":...}]`), PW aus Secret-Vault.

### 4.2 Neuer Aggregat-Endpoint: `routes/overview.py`
```
GET /admin/api/overview   (Depends(require_auth))
```
Bündelt **ohne neue Persistenz**:
- `dashboard`-Kennzahlen (Wiederverwendung der Logik aus `dashboard.py` — gemeinsame Funktion extrahieren),
- pro Host: Status + Tailscale + (optional Disk/RAM),
- pro App: name/host/last_status/last_deploy + `deploy_url`,
- pro Router-Instanz: `reachable`, Spokes (name/online/caps), aktive Routen, per-App-Quota-Auslastung, `default_traffic` (unregistrierte Consumer),
- `alerts[]` (abgeleitet, siehe §5).

Antwort-Schema als Pydantic-Modelle in `models.py` (`OverviewOut`, `RouterOverview`, `SpokeOut`, `AlertOut`).
Parallelisierung: die Router-Calls beider Instanzen via `asyncio.gather` (Gesamt-Timeout ~5 s).

### 4.3 Alerts-Ableitung (read-only, in `overview.py`)
Reine Funktion `derive_alerts(apps, hosts, routers) -> list[AlertOut]`:
- App `last_status in (down, degraded)` → `alert(level=error, …)`
- Host nicht `online` → `alert(level=error)`
- Router `reachable=False` → `alert(level=warn)`
- Spoke offline, der in einer aktiven Route referenziert ist → `alert(level=warn)`
- `default`-Traffic > 0 (unregistrierte Consumer) → `alert(level=warn)` (vgl. ai-router-Consumer-Audit)
- optional: Disk > 80 %, Token/Cert-Ablauf (falls Daten vorhanden)

---

## 5. Sektionen des Widgets (Frontend)

Neue View `frontend/src/views/OverviewView.vue` (oder Ausbau von `DashboardView.vue`), Pinia-Store `stores/overview.ts`, Polling 30 s über bestehenden `stores/poll.ts`.

1. **Ampel-Header** — grün/gelb/rot aus `alerts` (rot wenn ein error, gelb bei warn, sonst grün). Dieselbe Ampel speist optional das Tray (§7).
2. **Hosts** — NUC / CCX23 / **evo-x2** — online (Tailscale), SSH-ms, optional Disk/RAM, Health.
3. **Apps** — je App Status-Badge (healthy/down/degraded/unknown), letzter Deploy, **Deploy-Button** (`POST …/deploy`, mit Bestätigung über `stores/confirm.ts`) + Deep-Link in die App-Admin-UI.
4. **LLM-Router** (je Instanz NUC + CCX23) — Spokes online/offline + Caps (evo-x2 `qwen3.5:35b-fast`/`qwen3:14b`/`sarah-qwen36`/`bge-m3`, nuc-ollama/-reranker/-vision), aktive Routen, **per-App-Quota-Auslastung**, **`default`-Traffic-Warnung**.
5. **Alerts** — Liste aus `alerts[]`, je Eintrag Deep-Link zur Quelle (cockpit-App, ai-router-Admin, Host).

Deep-Link-Ziele: cockpit-eigene Views (`/admin/apps`, `/admin/hosts`, …), ai-router-Admin-UIs (`{router}/admin/`), Host-SSH-Hinweis.

---

## 6. Auth / Secrets

- cockpit braucht **read-only-Zugriff** auf beide ai-router-Admin-APIs. Token/PW in den **cockpit-Secret-Vault** (`secret_vault.py`, bereits verschlüsselt) — NICHT in `config.py` hardcoden.
- **Least-Privilege bevorzugt:** falls die ai-router-Admin-API ein read-only-Token-Konzept hergibt → das nutzen statt Voll-Admin-PW. Sonst Voll-Admin-PW im Vault, klar als „cockpit-overview-readonly" benannt.
- NUC-Router-PW: aus `ai-router/.env` (`LLM_ROUTER_ADMIN_PASSWORD`) einmalig in den Vault übertragen. CCX23-Router-PW analog.
- **Offene Entscheidung:** read-only-Router-Token einführen (kleine ai-router-Änderung) **oder** vorhandenes Admin-PW im Vault (schneller, weniger sauber). Empfehlung: Phase 1 mit Admin-PW im Vault starten, read-only-Token als Folge-Härtung (eigener Sanierungspunkt).

---

## 7. Tray (optional, Sekundär-Form)

Schlankes Menübar-/Tray-Statuslicht — **kein Voll-UI**, nur Ampel + Deep-Link auf das cockpit-Overview:
- **Variante A — `spoke-widget`** (Tauri, Rust+Vue, plattformübergreifend; bereits im Repo, Default-Port 7844 nach M1-Fix). Pollt `{cockpit}/admin/api/overview` → Ampel im Tray, Klick öffnet cockpit-Overview. Bevorzugt, weil plattformübergreifend (Mac/Win/Linux).
- **Variante B — SwiftBar** (`router/macos/`-Skripte, nur macOS) — minimaler Aufwand, aber Mac-only.

Empfehlung: Variante A, da der User NUC + MacBook + Windows nutzt.

---

## 8. Sequenzierung & Aufwand

| Schritt | Inhalt | Voraussetzung | Aufwand |
|---|---|---|---|
| **M11b** | evo-x2 als cockpit-Host aufnehmen (`bootstrap.py` + Host-Probe; evo hat eigenen systemd/HTTP-Pfad — ggf. spoke-stack-Health statt SSH) | — | S |
| **1** | `ai_router_client.py` (fail-soft, 2 Instanzen) + Vault-Eintrag NUC/CCX23-PW | M6 (Tokens), Vault | M |
| **2** | `routes/overview.py` Aggregat + Pydantic-Modelle + `derive_alerts` (dashboard-Logik refaktorieren/teilen) | Schritt 1 | M |
| **3** | `OverviewView.vue` + `stores/overview.ts` (Polling 30 s, 5 Sektionen, Deploy-Button via confirm) | Schritt 2 | M–L |
| **4** | Tray-Ampel (spoke-widget) gegen `/overview` | Schritt 2 | S–M |

Reihenfolge zwingend: **M11b → 1 → 2 → 3 → (4)**. Schritte 1–2 sind reines Backend (gut isoliert testbar), 3 ist Frontend.

---

## 9. Risiko & Tests

- **Risiko gesamt: niedrig.** Read-only-Aggregation + Deep-Links; einzige Schreib-Aktion ist das bereits existierende `deploy_app`. Kein Eingriff in Prod-Datenpfade.
- **Hauptrisiko:** ai-router-Admin-Auth/Endpunkt-Form weicht von Annahme ab → vor Schritt 1 die echte Admin-API gegen beide Instanzen verifizieren (1 curl je Endpoint mit PW).
- **Fail-soft zwingend:** offline Router-Instanz darf das Overview nicht 500en — pro Instanz `reachable:false` zurückgeben (Lehre aus `ai_router_reachable_false_alarm`).
- **Tests:** Unit für `derive_alerts` (reine Funktion, deterministisch); `ai_router_client` gegen Mock + 1 Integrationscheck gegen die laufende NUC-Instanz; Frontend manuell (beide Router online / einer offline / App down).
- **Deploy:** cockpit wird lokal gebaut (`cockpit:vX`) und per Image-Transfer + recreate auf CCX23 ausgerollt (kein GHCR-Pfad; Rollback = vorheriges `cockpit:v*`-Image + `compose.yaml.bak`).

---

## 10. Offene Entscheidungen (vor Start zu klären)

1. **Auth:** read-only-Router-Token (sauber, kleine ai-router-Änderung) vs. Admin-PW im Vault (schnell). → Empfehlung: PW im Vault starten.
2. **Host-Ressourcen (Disk/RAM):** im Overview anzeigen (zusätzliche SSH-Calls) oder bewusst weglassen (nur Status)?
3. **evo-x2-Probe (M11b):** SSH-ping oder spoke-stack-HTTP-Health (`/opt/spoke-stack`)? evo ist Docker-`ollama/ollama:rocm`.
4. **Tray:** spoke-widget (plattformübergreifend) vs. SwiftBar (Mac-only). → Empfehlung: spoke-widget.
5. **DashboardView ausbauen oder neue OverviewView?** → Empfehlung: neue `OverviewView` als „Single Pane", Dashboard bleibt schlanker Einstieg (oder Redirect).

---

## 11. UX & Lesbarkeit (Frontend-Detaildesign)

Leitsatz: **auf einen Blick erfassbar, ohne zu zoomen oder zu suchen.** Das Overview zeigt potenziell viel (3 Hosts, ~15 Apps, 2 Router, n Spokes, Alerts) — Lesbarkeit entscheidet, ob es genutzt wird. Aufbau strikt auf dem **vorhandenen cockpit-Designsystem** (kein neuer Stil).

### 11.1 Bestehende Komponenten wiederverwenden (Konsistenz = Lesbarkeit)
`Card`, `Badge`, `ProgressBar`, `Sparkline`, `EmptyState`, `Spinner`, `Modal`, `ConfirmDialog` sind vorhanden und werden 1:1 genutzt. Farb-/Theme-Tokens aus `style.css` (`--card-bg`, `--accent`, `--muted`) + das etablierte Status-Muster `bg-<farbe>-500/10 text-<farbe>-600 dark:text-<farbe>-400`. **Keine neuen Farben/Abstände erfinden.**

### 11.2 Status nie nur über Farbe (A11y + Scanbarkeit)
Jeder Status = **Punkt/Icon + Wort**, nie Farbe allein (Rot-Grün-Schwäche, S/W-Screens):
- healthy/online → grüner Punkt + „healthy"
- degraded/warn → amber Punkt + „degraded"
- down/offline → roter Punkt + „down"
- unknown/unreachable → grauer Punkt + „unbekannt"
`Badge` trägt Farbe **und** Text. Die Top-Ampel zusätzlich mit Icon (✓ / ! / ✕), nicht nur Kreisfarbe.

### 11.3 Typografie-Hierarchie (vom Bestand übernommen)
- Sektions-Titel: `text-sm font-semibold` + dezente Linie.
- Mikro-Labels: `text-xs font-semibold uppercase tracking-wider text-slate-500` (wie Dashboard-Kacheln).
- **Kennzahlen: `tabular-nums`** (gleiche Ziffernbreite → Spalten richten sich aus, springen beim Polling nicht).
- Technische Werte (IPs, Container, Caps): `font-mono text-xs`.
- Sekundärinfo in `--muted`; max. 2 Schriftgrößen pro Card.

### 11.4 Dichte & Gliederung
- **Card-Grid responsive:** `grid` mit `sm:grid-cols-2 xl:grid-cols-3`; auf Mobile 1-spaltig.
- Jede der 5 Sektionen (Ampel, Hosts, Apps, LLM-Router, Alerts) als eigener, klar abgesetzter Block mit Überschrift + Zähler (z. B. „Apps · 12 healthy / 1 down").
- Apps-Liste lang → kompakte **Tabellen-/Listenzeilen** (Name · Host · Status-Badge · letzter Deploy · Aktion), nicht 15 große Cards. Zeilenhöhe ruhig, ausreichend Padding, Zebra nur sehr dezent.
- Lange Werte (Beschreibungen, Fehlertexte) `truncate` + Volltext im `title`/Tooltip.

### 11.5 Quota & Metriken lesbar machen
- Per-App-Quota als `ProgressBar` **mit Zahl daneben** („72 % · 360/500 rpm") — Balken nie ohne Text.
- Schwellen-Einfärbung: < 75 % grün, 75–90 % amber, > 90 % rot (gleiche Semantik wie Status).
- Traffic-Trend optional als `Sparkline` (bereits vorhanden) statt großer Charts.
- `default`-Traffic-Warnung als eigene, deutlich beschriftete Zeile („3 unregistrierte Consumer auf `default`") mit Deep-Link — nicht in einer Zahlenwüste verstecken.

### 11.6 Polling ohne Flackern/Layout-Shift
- Beim 30-s-Refresh **alte Daten stehen lassen**, nur ein dezenter „aktualisiert vor Xs"-Hinweis + kleiner Spinner im Header. **Nie** Inhalt durch einen Vollbild-Spinner ersetzen (nur beim Erst-Load).
- Stabile Card-/Zeilenhöhen, damit nichts springt. `animate-fade-in` (vorhanden) nur beim Erst-Mount, nicht bei jedem Poll.

### 11.7 Fehler-/Offline-Zustände ruhig halten
- Router unreachable → **diese eine Router-Card** zeigt einen ruhigen „nicht erreichbar"-Zustand (grau, `EmptyState`-Stil), der Rest bleibt funktional. Kein globales Rot, kein Crash (Fail-soft aus §4.1).
- Erst-Load-Fehler: bestehendes rotes Info-Panel-Muster aus `DashboardView` (`border-red-300 … text-sm`) + „Erneut versuchen".
- Leere Sektionen → `EmptyState` mit erklärendem Satz, nicht leerer Block.

### 11.8 Aktionen & Deep-Links eindeutig
- Deploy-Button nur an der App-Zeile, mit `ConfirmDialog` (Bestätigung Pflicht, da Schreib-Aktion). Während Deploy läuft: Button disabled + Spinner + Toast-Feedback (`stores/toast.ts`).
- Deep-Links (zur ai-router-Admin-UI, App-Admin, Host) als klar erkennbare Links (`--accent`) mit „extern"-Indikator, damit Lesen ≠ Klicken verwechselt wird.

### 11.9 Dark-Mode-Parität & Fokus
- Beide Themes durchtesten (Kontrast der Status-Farben in `dark` über `…-400`-Varianten ist bereits gegeben).
- `focus-visible`-Outline (in `style.css` vorhanden) für alle interaktiven Elemente erhalten → Tastatur-Navigation lesbar.
- Mindest-Tap-Ziel 32 px, Tabellenzeilen mit genug Höhe.

### 11.10 Akzeptanzkriterien Lesbarkeit
- System-Gesamtzustand in **< 3 s** erfassbar (Ampel + Alerts oben).
- Jeder Status ohne Farbe verständlich (Wort/Icon vorhanden).
- Beim Auto-Refresh kein sichtbares Springen/Flackern.
- Lesbar auf 1280er-Laptop **und** in der Tray-/Mobil-Breite (responsive, kein horizontales Scrollen).
- Hell + Dunkel gleich gut lesbar (Kontrast AA).

---

## 12. Verifizierte ai-router-Admin-API (live gegen NUC :7849 geprüft)

> Ersetzt die Annahmen in §3/§4/§6. Identische Code-Basis auf CCX23 :7842 — Verträge dort gelten analog, vor Implementierung dort einmal smoke-prüfen.

### 12.1 Authentifizierung
**Single-Admin-Passwort** (`LLM_ROUTER_ADMIN_PASSWORD` env) → opakes Session-Token.

```
POST /admin/api/auth/login
Content-Type: application/json
Body: {"password": "..."}
↓ 200
{"token": "<43-char>", "expires_at": "<ISO-UTC>"}
```
Token-Gültigkeit: ~24 h. Nutzung als `Authorization: Bearer <token>` auf allen `/admin/api/*`. Bei 401 → Re-Login. Weitere Auth-Endpoints: `POST /admin/api/auth/logout` (204), `GET /admin/api/auth/me` (Session-Info). Vorhandenes Login-Konzept ist **token-basiert, nicht Cookie** — `httpx`-Client braucht keinen Cookie-Jar.

### 12.2 Endpoints (read-only, die wir brauchen)
| Endpoint | liefert | für cockpit-Overview |
|---|---|---|
| `GET /admin/api/health` | Gesamt-Health der Router-Instanz | Ampel pro Router |
| **`GET /admin/api/dashboard`** | **schon ein eigenes Aggregat** (Health + Counters + …) | Direkt mappen — spart Roundtrips |
| `GET /admin/api/dashboard/timeseries` | Zeitreihen (Sparkline-fähig) | optional, Sparkline |
| `GET /admin/api/spokes` | Liste `[{id, name, base_url, type, capabilities, tags, priority, status, last_check_at, gpu_info}]` | Spoke-Sektion (evo-x2/nuc-*) |
| `GET /admin/api/routes` | Liste `[{id, model_glob, spoke_id, spoke_name, priority, enabled}]` | Routen-Sektion |
| `GET /admin/api/apps` | App-Registry (für default-Traffic-Sicht) | Quota-/Consumer-Sektion |
| `GET /admin/api/quotas/{app_id}` | per-App-Quota-Detail | Quota-Bars |
| `GET /admin/api/audit`, `/logs` | Audit-Log, Logs | Alerts/Drilldown (optional, Phase 2) |

**Konsequenz für §4.1:** `AiRouterClient` wird kleiner als ursprünglich gedacht — `dashboard()` + `spokes()` + `routes()` reichen für Phase 1. `apps()` + `quotas(id)` für Phase 2 (Quota-Bars).

### 12.3 Konsequenz für §6 (Secrets)
- Vault-Eintrag heißt jeweils `ai-router-admin-pw-nuc` und `ai-router-admin-pw-ccx23` (Klartext-Passwort, der Client tauscht es selbst gegen ein Bearer-Token).
- **Token-Caching im Client:** in-memory mit Ablaufzeit aus `expires_at`, automatischer Re-Login bei 401 oder T-2min. Kein persistenter Token-Store nötig → cockpit-Vault hält nur die zwei PWs.
- Read-only-Token-Variante existiert nicht (Single-Admin-PW-Modell) → Phase 1 läuft mit Admin-PW; eine spätere read-only-Härtung wäre eine Änderung am ai-router (eigener Sanierungspunkt, nicht blockierend).

### 12.4 Fail-soft-Verhalten (verifiziert anwendbar)
- Login schlägt fehl (Router down/PW falsch) → Client setzt `reachable=False`, kein Throw nach außen.
- 401 nach erfolgreichem Login → einmal Re-Login, dann `reachable=False`.
- Timeout > 4 s → `reachable=False`. Pro Router-Instanz isoliert (Overview kippt nicht, wenn eine Instanz aus ist).
