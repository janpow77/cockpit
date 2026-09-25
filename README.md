# cockpit

Zentrales Verwaltungs-Tool fuer Multi-App-Multi-Host-Setup
(Workshop, audit_designer, llm-router, flowinvoice, hpp, qaaudit, ...).

## Domaenen (Phase 1)

1. **Apps** — Container-Status pro Host (NUC/CCX23/evo), Logs, Restart
2. **Hosts** — Tailscale-Health, SSH-Reachability
3. **GitHub** — Repos, PRs, CI-Runs (via GITHUB_TOKEN)
4. **Backups** — Job-Liste, On-Demand-Run, Restore-Test
5. **Secrets / Vault** — verschluesselt at-rest (Fernet), jede Reveal im Audit

## Stack

- FastAPI + SQLAlchemy + SQLite (`/data/cockpit.db`)
- Vue 3 SPA unter `/admin/` (vite + tailwind 4 + pinia)
- Bearer-Token-Auth (Single-Admin)
- paramiko fuer SSH-Befehle, lokale subprocess auf CCX23
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
AI_ROUTER_URL=http://ai-router:7842        # CCX23: gemeinsames Docker-Netz
AI_ROUTER_APP_ID=cockpit                  # eigener Quotenbereich, Standard: cockpit
AI_ROUTER_API_KEY=<optional>              # falls der Router API-Keys verlangt
```

Vor dem Cockpit-Deploy im Router eine aktive App `cockpit` mit 120 Anfragen/min
und 4 parallelen Anfragen anlegen (Admin-DB; YAML-Fallback in ai-router ebenfalls
pflegen). Ohne registrierte App wuerde der Router unbekannte Kennungen weiterhin
dem gemeinsamen `default`-Limit zuordnen. Der NUC nutzt als Router-Adresse
`http://127.0.0.1:7849` bei Host-Netzwerk.

Modellabrufe und Chat senden dieselbe App-Kennung. HTTP 429 wird als Ueberlastung
gemeldet; nur Verbindungsfehler fuehren zum naechsten konfigurierten Router-Ziel.
Die letzte erfolgreiche Modellliste bleibt bei Fehlern hoechstens fuenf Minuten
sichtbar und wird als nicht aktuell gekennzeichnet. Ein erfolgreicher leerer
Abruf entfernt die alte Liste. Telegram nutzt denselben differenzierten Status.

Warnungen verwenden stabile Kennungen ohne wechselnde Messwerte. Prozent-,
Alters- und Containerzahl-Aenderungen senden keine Entwarnung; ein Wechsel des
Schweregrads bleibt meldepflichtig. Vorhandene Alarmstaende werden beim Lesen
migriert. Ohne aktuellen Agenten-Heartbeat wird die fehlende Telemetrie gemeldet,
kein Host-Ausfall abgeleitet und kein alter Frischebefund als aktuell ausgegeben.

Erfolgreich beendete Compose-Dienste mit Suffix `-init` oder Label
`io.flowaudit.monitor.role=job` zaehlen nicht als ausgefallene Dauerlaeufer.
Zusaetzliche absichtlich gestoppte Dienste lassen sich in der Wand-Konfiguration
unter `inactive_services` pro Host/Projekt eintragen, z. B.
`{"nuc/audit_designer": ["frontend-dev"]}`. Die Ausnahme gilt nur fuer
`exited` mit Exit-Code 0; Fehler bleiben sichtbar. Die API nennt ausgeklammerte
Container weiterhin unter `ignored_stopped`.
