# System-Landschaft & Verantwortlichkeiten (Single Source of Truth)

> Stand: 2026-05-27 · Zweck: Einheitliche, widerspruchsfreie Tool-Landschaft.
> Eine Quelle pro Belang — Tools überschneiden sich NICHT.

## 1. Verantwortlichkeits-Matrix
| Belang | Kanonischer Owner | Rolle der anderen Tools |
|---|---|---|
| **Image-Build + Registry** | **lokal** `~/bin/ghcr-build-push.sh` → GHCR (Tags `latest`+`<sha>`) | **KEIN** GitHub-Actions-Build (Actions sparen). Owner janpow77. |
| **App-Deploy (pull + recreate)** | **cockpit** `POST /admin/api/apps/{id}/deploy` (implementiert) | per-project `deploy-*.sh` + manuelles `compose up` nur **Fallback**, nicht parallel |
| **Restart / Logs / Health / Status** | **cockpit** (Tailscale-SSH, kennt alle compose-Pfade) | sonst keiner für App-Container |
| **Deployment-Audit/Record** | **cockpit** `POST /admin/api/apps/{id}/deployments` (Hook-Token) | Build-Skript meldet Deploy an cockpit |
| **LLM / Embeddings / OCR / Rerank** | **ai-router** (`llm-router`) via `X-App-Id` | Apps reden NIE direkt mit Ollama-Spokes |
| **Knowledge / RAG + Zugriffsschutz** | **audit_designer VP-AI** (Daten-Eigentümer) | ai-router `/api/knowledge` proxyt nur; Filter/Privileg beim Eigentümer |
| **ML-Spoke-Registrierung + ML-Dienst-Restart (NUC)** | **spoke-agent** (:7844) | nur ML-Dienste (ollama/reranker/vision), **kein** App-Deploy |
| **Interaktive Host-Admin (Terminal/Files/Metrics/Webcam)** | **audit_designer `nuc_admin`** (via Proxy zur NUC) | „Hände an der Maschine"; **keine** Deploy-Restarts |
| **Terminal-Workspace** | **tmux auf der NUC** (eine Session-Quelle) | Web/iTerm2/Windows = Clients derselben Session |
| **tmux-/Dotfiles-Config** | **`router/dotfiles/tmux.conf`** (versioniert) → symlink `~/.tmux.conf` | keine separate `~/.tmux.conf` |
| **Secrets** | **cockpit-Vault** (Fernet, Quelle der Wahrheit) | Übernahme in `/etc/<app>/env` (chmod 600); aktuell manuell |
| **Cloud-/Infra-Tokens (Hetzner, Cloudflare, GitHub/GHCR)** | **cockpit-Vault** (zentral, scoped) | **API-Tokens** (Hetzner hcloud, Cloudflare API, **GitHub/GHCR-PAT**) zentral & repo-übergreifend nutzbar; **per-Tunnel `TUNNEL_TOKEN` bleibt pro App**. GitHub heute mehrfach: gh-Keyring (`gho_`, write:packages) + docker-config ghcr + cockpit `GITHUB_TOKEN` → konsolidieren. Least-Privilege/scoped, nie hardcoden. |
| **VPN / Netz** | **Tailscale-Mesh** (intern Tailscale-only) | GL.iNet-`router` = Reise-Gateway (German IP), kein App-Deploy |
| **Monitoring-Anzeige** | **cockpit** (Apps/Hosts-Health) | router-macOS-Widgets = read-only Statusanzeige |

## 2. Kanonischer Deploy-Flow (verbindlich)
```
1. Code commit (Feature-Branch)
2. Image bauen + pushen:   ~/bin/ghcr-build-push.sh <repo>     # LOKAL, 0 Actions-Minuten
3. Auf Host aktualisieren: pull + up -d (--force-recreate bei env-Änderung)
                           → Ziel: über cockpit (siehe Lücke §3); bis dahin per-Host
4. Deploy melden:          cockpit Deployment-Record (Hook-Token)
5. Verifizieren:           cockpit Health/Logs/Status
```
- **Build = immer lokal** (`ghcr-build-push.sh`). GitHub-Actions-Build ist bewusst deaktiviert/zu vermeiden.
- **Secrets**: in cockpit-Vault pflegen → in `/etc/<app>/env` übernehmen → `--force-recreate`.

## 3. Status / offene Punkte
- **App-Deploy (pull+recreate) implementiert:** `docker_inspect.deploy_app()` + Route `POST /admin/api/apps/{id}/deploy` (Query: `pull`, `force_recreate`), Audit `app.deploy`. Damit ist cockpit der eine Deploy-Hub. **Rollout:** cockpit selbst muss dafür noch auf CCX23 neu deployt werden (Image bauen → `docker save | ssh | docker load` → `compose up`, siehe cockpit-README).
- **Deployment-Record bleibt Aufgabe der Build-Pipeline:** `ghcr-build-push.sh` meldet image+sha an `POST /deployments` (Hook-Token); die Deploy-Aktion selbst kennt keinen sha → kein Doppel-Record.
- **Vault → env-Sync ist manuell.** Optional später: cockpit-Action „env materialisieren" (Vault → `/etc/<app>/env`).

## 4. Aufgelöste Widersprüche
1. **Container (re)starten** ging über 4 Wege (cockpit / spoke-agent / nuc_admin-docker / manuelles SSH). → **cockpit** ist kanonisch für App-Container; **spoke-agent** nur ML-Dienste; **nuc_admin-docker** nur Read/Debug, keine Deploy-Restarts.
2. **Deploy-Methode** uneinheitlich. → **build lokal → recreate (Ziel cockpit) → record in cockpit**. Kein ad-hoc-SSH-compose als Standard.
3. **Secret-Orte** (Vault / `/etc/*/env` / `.env`). → **Vault = Quelle**, env = abgeleitet.
4. **Doppelte audit_designer-Instanzen** (NUC `audit_designer`/DB `audit_designer` + CCX23 `checklist`/DB `checklist`, unterschiedliche `SECRET_KEY`). → Bewusster Sonderfall (Voraussetzung NUC-Admin-Proxy). Kein gemeinsamer User-Token → Service-Key-Bridge. Nicht versehentlich Daten divergieren lassen.
5. **GHCR-Build** nicht über GitHub Actions → lokal (`ghcr-build-push.sh`).

## 5. Hosts & Apps (aus cockpit `bootstrap.py`, Stand verifiziert)
- **NUC (100.102.132.11, Tailscale):** audit_designer (`~/Projekte/audit_designer/docker-compose.yml`, DB `audit_designer`, :8003 lokal), auditworkshop, flowinvoice, hpp, qaaudit, backfill; ai-router(:7849 knowledge), spoke-agent(:7844); tmux-Server (Sessions main/audit/work).
- **CCX23 (100.99.159.80, self-host):** checklist (=audit_designer, DB `checklist`), auditworkshop (`/opt/auditworkshop/compose.yaml`), llm-router (`/opt/llm-router/compose.yaml`, :7842), cockpit (:7843, Tailscale-only), flowinvoice.
- **evo-x2 (`evo2`, Tailscale 100.81.4.99):** **PRIMÄRER LLM-Backend** — die Router-Routen `qwen3:14b`/`qwen3.5:*`/`sarah-qwen36*` zeigen alle hierher. ollama läuft als **Docker-Container** (`ollama/ollama:rocm`, Compose `/opt/spoke-stack/`, `restart=unless-stopped`, getunt: NUM_PARALLEL=2/MAX_LOADED=4/KEEP_ALIVE=24h, ROCm-Env), serviert qwen3.5:35b-fast/qwen3:14b/sarah-qwen36/qwen3.5:9b-fast/bge-m3. Separate **llama.cpp-systemd-Dienste :8080–8083** (Mistral/Qwen32B/Embed/OCR) — meist down, **nicht** vom Router genutzt; evo-metrics :8084 up. `llama-update.timer` aktuell NICHT aktiv. **NICHT in cockpit-bootstrap** → zentral unüberwacht (nur via Router-Spoke-Health). evo-gpu-llm-manager :7842 = offline (M14 disabled).
- **Konsequenz:** drei Hosts (NUC, CCX23, **evo-x2**), aber cockpit kennt nur NUC+CCX23 → evo-x2 (kritischster LLM-Backend) fehlt im zentralen Monitoring (s. Audit F10).

## 6. Verweise
- **Gestaffelter Umsetzungs-Fahrplan (mit Gates + Pre-Flight):** `cockpit/docs/sanierung-fahrplan.md` — Stufe 0 (Tokens/SSH/Tailscale/Backups testen) → Stufen 1–4
- **Konsistenz-Audit + Maßnahmen:** `cockpit/docs/konsistenz-audit-und-sanierung.md` — verifizierte Widersprüche (F0–F16) + Maßnahmen (M0–M18)
- NUC-Admin-Proxy + tmux + Celery-Fix: `audit_designer/docs/nuc-admin-hetzner-proxy-todo.md`
- RAG-Zugriffsschutz (is_efre_hessen): `audit_designer/docs/vp-ai-rag-zugriffsschutz-todo.md`
- Build/Push: `~/bin/ghcr-build-push.sh`, `~/bin/local-ci.sh`
