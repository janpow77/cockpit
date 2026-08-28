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
```

## Aufträge (Kanban)

Die Seite `/kanban` führt Agentenläufe als Karten (Auftragstext, Projekt, Agent, Profil,
Priorität). Je Auftrag entsteht ein Git-Worktree `<projekt>/.cockpit-auftraege/wt-<id>` mit
Branch `auftrag/<id>`; Spalten Eingang → Geplant → Läuft → Rückfrage/Freigabe → Fertig,
Detailpanel mit Ergebnis, Kosten, Diff-Link, Protokoll und „Nachfrage“ (setzt die Sitzung fort).

**Agenten:** Claude Code, Codex, Gemini (über die Antigravity-CLI `agy`); Programmpfade
absolut in der Einstellung `agent_bins`.

**Vorgehen je Auftrag** (`modus`): **nur berichten** (analysieren und einen Plan vorschlagen,
immer nur lesend) · **Plan mit Freigabe** (Vorgabe: erst der Plan, die Karte landet in
„Rückfrage / Freigabe“; „Umsetzen“ setzt dieselbe Sitzung mit dem Schreibprofil fort) ·
**direkt umsetzen** (ohne Zwischenschritt).

**Profile:** `lesen` (nur Lesen, git/gh/rg), `bearbeiten`, `bearbeiten_tests` (zusätzlich
npm/pytest/ruff/git commit), `voll` – wirksam nur in der Umsetzungsphase; Absicherung bleibt
der eigene Worktree samt Branch.

**Vorlagen:** 31 vorgefertigte Aufträge (Repo prüfen, Tests ergänzen, Sicherheits-Audit, Doku,
Barrierefreiheit …) mit hinterlegtem Modus; `{projekt}` wird ersetzt, eigene über `auftrag_vorlagen`.

**Automatische Vorschläge:** „Vorschläge einholen“ wertet Git-Verlauf, GitHub (`gh`), die
graphify-Analyse und den Code aus; daraus legt der Runner Karten „Vorschlag: …“ in den
Eingang – wöchentlich je aktivem Projekt oder auf Abruf (Einstellung `vorschlaege`).
