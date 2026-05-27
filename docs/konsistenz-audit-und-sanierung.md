# Konsistenz-Audit & Sanierungsplan (One-Shot)

> Stand: 2026-05-27 · Lokal verifiziert auf der NUC (kein GitHub-Stand) · ergänzt Codex-Audit.
> Ziel: ALLE Tool-Widersprüche in EINER koordinierten Sanierung beheben. Status: **PLAN — nichts geändert.**
> Begleitdoc: `system-landschaft.md` (Verantwortlichkeits-Matrix).

## A0. AUTORITATIVE KORREKTUR — Live-Admin-DB schlägt YAML (Nachtrag 2026-05-27)
**Wurzelursache aller Verwirrung gefunden:** Die Router-Wahrheit steht in der **Admin-DB** (`/data/admin.db`, Tabellen `admin_apps`/`admin_spokes`/`admin_routes`), **NICHT** in den `config.*.yaml`. Die YAML ist nur Fallback („wenn admin-DB leer"). Live-Stand:
- **NUC-Router:** `admin_apps` **LEER** → Apps aus YAML (audit_designer, flowinvoice, auditworkshop, love-ai, krypto, test, default). `admin_routes` = nur **3** (`qwen3:14b`, `qwen3.5:*`, `sarah-qwen36*` → evo-x2). Knowledge-Spoke `audit-designer-kb` → `audit_designer_backend:8000`.
- **CCX23-Router:** `admin_apps` = **2** (`auditworkshop`@240, **`checklist`@600, enabled**). `admin_routes` = **17** (inkl. `qwen2.5:*` enabled, `love-ai-*`, `love-ai-32b-fast`, reranker/ocr; `gpt-*`/`text-embedding-*`/`qwen3:30b*` disabled).

**Konsequenzen — Korrekturen an §B:**
- **F1 = FEHLALARM.** `checklist` IST registriert (CCX23-Admin-DB, 600rpm) → audit_designer-CCX23 läuft NICHT auf Default-Quota. (Mein YAML-basierter Befund war falsch — config.ccx23.yaml ist stale.)
- **F3 = reframed.** Keine „tote YAML-Route"; live routet CCX23 `qwen2.5:*` (enabled), aber **kein Spoke serviert qwen2.5** (evo-x2/nuc-ollama haben es nicht) → flowinvoice→qwen2.5 scheitert am Spoke. NUC hat gar keine qwen2.5-Route.
- **F5 = downgrade.** Tabelle `qchess_report` existiert in der Live-DB NICHT → keine 768-Vektoren; reiner Code-Latenz-Befund. `kb_chunks` = 1,43 Mio @ 1024 (korrekt).
- **F8 = korrigiert.** flowaudit = Router(7842)+Direct(11434); flownavigator = Direct-11434; **kiraclaw = KEIN LLM-Router-Consumer** (raus).

**NEUE Befunde aus der Verifikation:**
- **F0 (Hoch, Wurzel):** YAML ↔ Admin-DB divergieren; welche Quelle gewinnt, unterscheidet sich **pro Host UND pro Tabelle** (NUC-Apps: YAML; CCX23-Apps: DB; Spokes/Routes: immer DB). Editieren der YAML-Spokes/Routes ist **wirkungslos** (no-op) → stiller, irreführender Drift. **DIE zentrale Inkonsistenz.**
- **F14 (Mittel):** Die beiden Router-Route-Tabellen divergieren stark (NUC 3 vs CCX23 17 Routen) — kein gemeinsamer Stand.
- **F15 (Niedrig):** Tote Spokes registriert: `nuc-gpu-llm-manager` + `evo-gpu-llm-manager` (:7842, capability compute) = OFFLINE (ConnectError), noch in admin_spokes.
- **F13 (Mittel):** `spoke-widget` Default `agent_url=http://localhost:7700`, aber spoke-agent läuft auf **:7844** → Tray-Widget erreicht den Agent mit Defaults nicht. (macOS `llm-router-status.60s.sh` zielt dagegen korrekt auf CCX23:7842.)

**Empirische Consumer (metrics.db `requests`, tatsächlicher Traffic):**
- **NUC:** audit_designer 23025 · **default 452** · auditworkshop 337 · krypto 334 · love-ai 180 · test 48.
- **CCX23:** **default 6626** · checklist 1906 · auditworkshop 114 · audit_designer 9 · flowinvoice 1.
→ **F2 (reframed, Hoch):** Es gibt erheblichen **`default`-Traffic** (CCX23 **6626**, NUC 452) = Requests ohne registrierten/zugeordneten app_id → Default-Quota (30rpm) + keine Zuordenbarkeit. Quelle identifizieren (welcher Client sendet als `default`?) und labeln/registrieren. **app_id-Drift live:** CCX23 sieht `checklist` (1906) UND `audit_designer` (9) → derselbe logische Dienst unter zwei IDs.

**Repo-vs-Live:** ai-router `config.nuc.yaml` ist live gemountet (`/etc/llm-router/config.yaml`) + git clean — aber durch die Admin-DB überstimmt (s. F0). cockpit hat die `deploy_app`-Änderung uncommitted (Branch `feat/cloudflare-fallback-docs`), Rollout offen.

---

## A. Verifizierte Grundwahrheit (Belege) — (YAML-Sicht, durch A0 teils überholt)
- **Router-registrierte app_ids** (`ai-router/config.nuc.yaml`): default, audit_designer, flowinvoice, auditworkshop, love-ai, krypto, test. CCX23 (`config.ccx23.yaml`): default, auditworkshop, test.
- **NICHT registriert (aber Consumer):** `regulierung`, `flowaudit`, `flownavigator`, `kiraclaw`, **`checklist`** (= audit_designer auf CCX23).
- **Spoke-Modell-Inventar (live):** evo-x2 `[sarah-qwen36:latest, qwen3.5:35b-fast, qwen3:14b, qwen3.5:9b-fast, bge-m3]`; nuc-local `[qwen3:8b, bge-m3]`; nuc-vision `[donut-cord-v2, tesseract]`; nuc-reranker `[BAAI/bge-reranker-v2-m3]`.
- **Tote Route:** `config.nuc.yaml:117 model_glob "qwen2.5:*"` — kein Spoke serviert qwen2.5.
- **Port-Semantik (host-abhängig):** NUC ai-router = **7849** (7842 tot); CCX23 = `llm-router:**7842**` (OpenAI /v1), 7849 nur Knowledge-Proxy→NUC.
- **cockpit überwacht** (`bootstrap.py`): audit_designer, auditworkshop, backfill, checklist, flowinvoice, hpp, llm-router, qaaudit.
- **Laufend, aber NICHT überwacht:** krypto, love-ai, flowsearch, riskanalysis, flowaudit.
- **Embedding-Standard:** bge-m3 / 1024.

## B. Befund-Matrix (verifiziert ✓ / Codex-GitHub ~)
| ID | Befund | Sev | Status |
|---|---|---|---|
| F1 | audit_designer/CCX23 `X-App-Id: checklist` nicht im CCX23-Router registriert → Default-Quota (30rpm/2) | Hoch | ✓ |
| F2 | `regulierung` sendet kein X-App-Id + 11434-Fallback → Default-Quota | Hoch | ✓ |
| F3 | Tote Route `qwen2.5:*`; flowinvoice-Default `qwen2.5:7b/1.5b` → kein Spoke → Fehler | Hoch | ✓ Route, ~flowinvoice |
| F4 | `krypto` Embedding-Default `nomic-embed-text` (768, kein Spoke) vs Standard bge-m3/1024 | Hoch | ✓ |
| F5 | audit_designer `qchess_report.embedding=Vector(768)` vs kb_chunks/memory `1024` | Mittel | ✓ |
| F6 | Direct-Bypass: audit_designer `OLLAMA_BASE_URL=100.81.4.99:11434` + Eval/Notebook/Tasks 11434 | Mittel | ✓ |
| F7 | Kein kanonischer Router-Port (7842 CCX23 / 7849 NUC); love-ai erwartet `ai-router:7842` (NUC=7849) | Mittel | ✓ |
| F8 | Unregistrierte Consumer flowaudit/flownavigator/kiraclaw (falls Router-Aufruf) → Default-Quota | Mittel | ~ verifizieren |
| F9 | Compose-Mehrdeutigkeit: flowinvoice (4), love-ai (3), audit_designer (prod+base) | Mittel | ~ |
| F10 | Monitoring-Lücke: krypto, love-ai, flowsearch, riskanalysis, flowaudit nicht in cockpit; **evo-x2 ist gar kein cockpit-Host** (nur nuc+ccx23) → primärer LLM-Backend zentral unüberwacht | Hoch | ✓ |
| F16 | evo-x2 hat eigenen täglichen Auto-Update (`llama-update.timer`) → Übernacht-Änderungsrisiko (wie Watchtower auf NUC) | Mittel | ✓ |
| F17 | ai-router Admin-PW. **NUC: war Fallback „admin" → ✓ behoben** (S2, via .env, admin→401). **CCX23: bereits gesichert** (S3-Verifikation: PW gesetzt, admin→401) — kein Handlungsbedarf. | Hoch | ✓ erledigt |
| F18 | `default`-Traffic = fast nur `bge-m3`-Embeddings (/api/embed, ~438) — ein Embedding-Client sendet kein `X-App-Id` → Default-Quota | Mittel | ✓ (S2 verifiziert) |
| F11 | Zwei audit_designer-Instanzen (DB audit_designer/NUC + checklist/CCX23, versch. SECRET_KEY) | Mittel | ✓ strukturell |
| F12 | Secrets verstreut (Vault nicht als Quelle erzwungen) | Niedrig | ~ |

## C. Sanierungs-Maßnahmen (präzise, atomar, batchbar)
Pro Maßnahme: Ort · Änderung · Verifikation · benötigt Redeploy?

### Gruppe 0 — Config-Quelle vereinheitlichen (WURZEL, zuerst!)
- **M0 (F0,F14):** Admin-DB als **Single Source of Truth** etablieren. Konkrete Schritte:
  1. **Export-Skript** `ai-router/scripts/dump_admin_config.py`: liest `admin_apps/admin_spokes/admin_routes/admin_quotas` aus `/data/admin.db` → versionierte JSON/YAML pro Host (`config/admin-export.nuc.json`, `…ccx23.json`). Im Repo eingecheckt = die wahre, nachvollziehbare Quelle.
  2. **Re-Seed/Import-Skript** `apply_admin_config.py` (idempotent, upsert by id): spielt die versionierte Quelle in die Admin-DB ein. Damit ist „Repo → Live" reproduzierbar.
  3. **YAML stilllegen:** `config.nuc.yaml`/`config.ccx23.yaml` Kopf-Kommentar „NUR Erst-Seed/Fallback — NICHT live; Wahrheit = admin.db, gepflegt über Admin-UI/apply_admin_config.py". Optional: beim Start warnen, wenn YAML≠admin-DB.
  4. **Drift-Check** (cron/cockpit): `dump_admin_config.py` vs eingecheckter Stand → Alarm bei Divergenz.
  5. **NUC↔CCX23 abgleichen** (F14): bewusst entscheiden, welche Routen/Apps auf beiden Hosts identisch sein müssen (z.B. embedding/rerank/ocr) vs. host-spezifisch.
  - Regel danach: **alle Router-Änderungen via Admin-API/apply-Skript**, nie YAML editieren (no-op).
  - **Default-Traffic-Quelle (F2) identifizieren:** `metrics.db` nach `route`/`spoke`/`ts` der `default`-Requests gruppieren + Client-seitig (welche App sendet kein/falsches X-App-Id) zuordnen → registrieren/labeln.
  - Verif.: eingecheckter Export == Live-`admin_*`; `default`-Requests → ~0 nach Registrierung.

### Gruppe 1 — ai-router-Registry (über Admin-API/DB, dann Cache-Reload)
- **M1 (F1 — AUFGELÖST):** Keine Aktion nötig — `checklist`@600rpm ist in der CCX23-Admin-DB registriert. Optional: app_id-Namensdrift `checklist` (CCX23) vs `audit_designer` (NUC) vereinheitlichen, damit Stats/Quota nicht gespalten sind.
- **M2 (F2,F8):** Auf der **NUC** (admin_apps leer→YAML) Consumer mit eigener App+Quota anlegen, die den NUC-Router nutzen: `regulierung`, `flowaudit`. (`flownavigator` = Direct-11434 → erst über Router routen; `kiraclaw` = kein Consumer.) Verif.: Router-Stats zeigen die App statt `default`.
- **M3 (F3):** flowinvoice-Default-Modell von `qwen2.5:*` auf einen **servierten** Tag umstellen (`qwen3.5:35b-fast`/`qwen3:14b`) — qwen2.5 liegt auf keinem Spoke (Route allein hilft nicht). Verif.: Generate ok. Optional `qwen2.5:*`-Route deaktivieren.
- **M14 (F15):** Tote Spokes `nuc-gpu-llm-manager` + `evo-gpu-llm-manager` (:7842, offline) aus admin_spokes entfernen/deaktivieren. Verif.: keine offline-compute-Spokes mehr.
- **M15 (F13):** `spoke-widget` Default `agent_url` auf **:7844** korrigieren (oder spoke-agent auf 7700 vereinheitlichen) — Repo `spoke-widget` (Settings-Default) + Doku. Verif.: Tray-Widget erreicht den Agent ohne manuelle Einstellung.

### Gruppe 2 — Per-App-Config/ENV (env-Änderung → `--force-recreate`)
- **M4 (F2):** `regulierung` — X-App-Id+X-Api-Key-Header im LLM-Client setzen; `OLLAMA_URL` host-korrekt auf den Router (NUC 7849), 11434-Fallback entfernen. Ort: `regulierung/backend/app/.../ollama*`. Verif.: Router-Stats zeigen `regulierung`.
- **M5 (F4):** `krypto/backend/app/core/config.py:44` `ollama_model_embed` → `bge-m3`. Prüfen, ob bestehende krypto-Embeddings (768/nomic) re-embedded werden müssen. Verif.: Embedding-Dim=1024.
- **M6 (F3):** `flowinvoice` Default-Modell `qwen2.5:*` → servierter Tag (`qwen3.5:35b-fast` o. `qwen3:14b`). Orte: `flowinvoice/.../config.py`, `docker/docker-compose.yml`. Verif.: Generate ok.
- **M7 (F6):** audit_designer — `OLLAMA_BASE_URL=100.81.4.99:11434` → Router; Eval/Notebook/Tasks-Defaults (kb_rag_service, memory_embedding, vpai_notebook, evaluation/*, tasks/*) auf Router-URL/env umstellen oder als Dev-only kennzeichnen. Verif.: kein 11434 im Prod-Pfad.
- **M8 (F7):** Router-Adressierung vereinheitlichen: love-ai (& alle) auf den **host-korrekten** Router-Endpunkt (NUC 7849 / CCX23 7842) per zentralem env. Optional: NUC-ai-router zusätzlich auf 7842 lauschen lassen, damit ein Port-Schema gilt. Verif.: love-ai erreicht den Router.

### Gruppe 3 — audit_designer Schema (Alembic + Re-Embed)
- **M9 (F1,F11):** app_id-Strategie festlegen (Empfehlung: überall `audit_designer`); env beider Instanzen + Router-Registrierung angleichen. Sonderfall „zwei Instanzen" dokumentieren (Datendivergenz vermeiden).
- **M10 (F5):** Alembic-Migration `qchess_report.embedding` 768→1024 (oder Spalte entfernen, falls ungenutzt) + Re-Embed mit bge-m3. Verif.: `\d qchess_report` zeigt vector(1024); Suche funktioniert.

### Gruppe 4 — cockpit Monitoring (bootstrap + reseed)
- **M11 (F10):** `cockpit/src/cockpit/services/bootstrap.py` Apps ergänzen: krypto, love-ai, flowsearch, riskanalysis, flowaudit (host=nuc). Reseed/neu starten. Verif.: cockpit listet alle laufenden Apps.
- **M11b (F10, evo-x2):** **Dritten Host `evo-x2` (100.81.4.99) in cockpit aufnehmen** (Hosts-Domain + SSH/Tailscale) und seine Dienste (ollama :11434, llama-* systemd :8080–8084, webhook :9000) als überwachte Einheiten. Da systemd statt Docker: Health-Probes (HTTP/`systemctl`-Status via SSH) statt `docker ps`. Verif.: evo-x2 erscheint mit Health in cockpit; LLM-Backend zentral sichtbar.
- **M16b (F16):** evo-x2 `llama-update.timer` (täglich) bewusst steuern — Wartungsfenster/Pinning, damit Auto-Updates den LLM-Backend nicht unkontrolliert ändern (analog Watchtower-Policy auf NUC). **Hinweis (verifiziert):** der Timer ist aktuell NICHT aktiv (0 timers) — kein akutes Übernacht-Risiko.
- **M11c (evo-x2 ollama) — OBSOLET/aufgelöst (S2-Verifikation 2026-05-27):** Der frühere Befund „bare-Prozess auf Defaults ohne Auto-Restart" war ein **Misread** (Host-`ps` zeigte den Prozess eines Docker-Containers). Realität: ollama ist ein **Docker-Container** (`ollama/ollama:rocm`, Compose `/opt/spoke-stack/compose.yaml`+`compose.amd.yaml`), **`restart=unless-stopped`** (Auto-Restart ✓) und bereits getunt: `OLLAMA_NUM_PARALLEL=2`, `OLLAMA_MAX_LOADED_MODELS=4`, `OLLAMA_KEEP_ALIVE=24h`, `OLLAMA_HOST=0.0.0.0`, ROCm-Env (`HSA_OVERRIDE_GFX_VERSION=11.5.1`). → **Keine systemd-Maßnahme nötig** (hätte mit dem Container um Port 11434 kollidiert). Optional später: NUM_PARALLEL höher (Recreate via spoke-stack-Compose). `evo-health-monitor.service` FAILED bleibt ein separater Minor-Punkt.

### Gruppe 7 — Betriebs-Hygiene
- **M17 (CCX23-Image-Müll):** Periodischer `docker image prune -f` auf CCX23 (Cron oder cockpit-Action), da CCX23 **kein** Watchtower mit `CLEANUP=true` hat (anders als NUC) → alte `:latest`-Versionen sammeln sich als dangling Images an. Einmalig bereits ausgeführt (2026-05-27: 91 %→76 %, ~22 GB frei). Optional `-a` für getaggte Alt-Images (16,7 GB reclaimable). Verif.: Disk < 80 %, dangling ≈ 0.

### Gruppe 8 — Ausbau (NACH dem Fundament)
- **M18 (Overview-Widget, NICHT vor M0/M11):** Das vorhandene ai-router-/Status-Widget zu einem **read-only „Single Pane of Glass"** ausbauen: aggregiert Status aus **cockpit** (Apps/Hosts-Health) + **ai-router** (Spokes/Routen/Quota) + den 3 Hosts (NUC/CCX23/evo-x2), mit **Deep-Links** in die Admin-UIs. **KEIN eigener Konfigurator** — Schreib-/Config-Hoheit bleibt bei cockpit (Management) + ai-router-Admin (Registry/SoT), sonst neuer Drift (vgl. F0). **Voraussetzung:** M0 (eine Quelle) + M11/M11b (cockpit kennt alle Apps + evo-x2) müssen zuerst stehen, sonst zeigt das Widget divergente Daten. Reihenfolge daher: Fundament → dann Widget als Sichtebene.

### Gruppe 5 — Compose-Hygiene (Doku/Cleanup)
- **M12 (F9):** Pro Repo EINE kanonische Compose je Zielhost benennen (Header-Kommentar „CANONICAL"), Legacy-Varianten markieren/entfernen. Betrifft flowinvoice, love-ai, audit_designer.

### Gruppe 6 — Secrets & Cloud-Tokens (optional, danach)
- **M13 (F12):** Prod-Secrets aller Consumer auf cockpit-Vault als Quelle verweisen; Dev-Defaults klar als Dev-only.
- **M16 (NEU — zentrale Cloud-/Infra-Tokens):** Ziel: Hetzner- und Cloudflare-Tokens **einmal** im cockpit-Vault, repo-übergreifend nutzbar. **Wichtige Unterscheidung:**
  - **API-Tokens** (Hetzner hcloud-API, Cloudflare-API für DNS/Tunnel-Management) → **zentral in den Vault**, von allen Repos/Tooling (cockpit) referenziert statt verstreut. **Scoped/Least-Privilege** (Cloudflare: nur Zone-DNS+Tunnel; Hetzner: nur Projekt). 
  - **Per-Tunnel `TUNNEL_TOKEN`** (audit_designer/nuc/kira/checklist cloudflared) → **bleibt pro App/Tunnel** (jeder Named Tunnel hat seinen eigenen; NICHT zusammenlegen). Nur den Speicherort (Vault → env) vereinheitlichen.
  - **Bestand heute:** Cloudflare-Refs in audit_designer, Workshop; Hetzner-Refs in ai-router, audit_designer, cockpit, spoke-agent; laufende cloudflared: audit_designer/nuc/kira (NUC) + checklist (CCX23).
  - **GitHub/GHCR:** Heute **mehrfach/überlappend** — gh-CLI-Keyring-Token (`gho_`, Scopes repo/workflow/write:packages), `~/.docker/config.json` ghcr.io-Cred, cockpit `GITHUB_TOKEN` (PAT). → **Konsolidieren:** EIN scoped GitHub-Token im Vault: `write:packages` (GHCR-Push via ghcr-build-push.sh) + `read:org`/`repo:status` (cockpit GitHub-Ansicht). Möglichst Fine-grained-PAT statt Classic, mit Ablaufdatum + Erneuerungs-Reminder. Repos referenzieren nur `ghcr.io/janpow77/*` (Pull braucht ggf. read:packages, falls private).
  - **⚠️ Risiko „überall nutzbar":** großer Blast-Radius bei Leak → deshalb scoped Tokens + Vault-only (kein Klartext in Repos), Reveal auditiert. GitHub-Token-**Ablauf** beachten: läuft der GHCR-Cred ab, scheitern Pulls privater Images bei Container-Neustarts/Watchtower.
  - Verif.: ein Token-Satz je Anbieter im Vault; kein Hetzner/Cloudflare/GitHub-Token mehr im Klartext in Repos/env; Tunnel + GHCR-Pull/Push funktionieren weiter.

## D. One-Shot-Ausführungsreihenfolge (koordiniert)
1. **Vorbereiten (kein Live-Impact):** alle Config/Code-Änderungen M1–M12 committen (Feature-Branches je Repo), Images bauen wo nötig (`ghcr-build-push.sh`, lokal).
2. **Router zuerst** (M1–M3): `config.nuc.yaml` + `config.ccx23.yaml` → ai-router NUC + CCX23 neu deployen. (Registrierung MUSS vor App-Umstellung stehen, sonst 401/Default.)
3. **Apps** (M4–M9): env/Code-Änderungen → betroffene App-Container `--force-recreate` (über cockpit, sobald Deploy-Aktion ausgerollt; sonst per-Host).
4. **Schema** (M10): Alembic-Migration + Re-Embed in audit_designer (Wartungsfenster, da Re-Embed läuft).
5. **cockpit** (M11): bootstrap erweitern → cockpit neu deployen → Monitoring vollständig.
6. **Cleanup/Secrets** (M12–M13): Compose-Hygiene + Vault-Anbindung.
7. **Verifikation gesamt:** Router-Stats zeigen alle Consumer mit eigener Quota; keine `qwen2.5`/`nomic`/11434-Treffer im Prod-Pfad; cockpit überwacht alle laufenden Apps; Embedding überall 1024.

## E. Offene Verifikationen vor Umsetzung
- F8: tatsächlich Router-Consumer? (flowaudit/flownavigator/kiraclaw lokal prüfen — Codex las GitHub.)
- M5/M10: Re-Embed nötig (bestehende Vektoren) — Umfang/Downtime klären.
- M8: NUC-Router zusätzlich auf 7842 — gewünscht oder env-Vereinheitlichung bevorzugen?
