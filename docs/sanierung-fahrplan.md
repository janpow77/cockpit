# Sanierungs-Fahrplan (gestaffelt, mit Gates) — Systemlandschaft

> Stand: 2026-05-27 · Status: **PLAN — nichts ausgeführt** · gehört zu `konsistenz-audit-und-sanierung.md` (Befunde F0–F16, Maßnahmen M0–M18) und `system-landschaft.md`.
> **Kein One-Shot.** Programm über ein Wartungsfenster, Stufe für Stufe, jede mit Gate + Rollback. Jede Stufe wird von Jan einzeln freigegeben.

## Globale Regeln
- **Reihenfolge ist bindend.** Keine Stufe ohne grünes Gate der Vorstufe.
- **Off-Peak** (kein laufender Workshop/Termin).
- **Vor jeder 🔴-Stufe:** Backup + Rollback-Schritt notiert + getestet.
- **Ein Schritt nach dem anderen**, nach jedem verifizieren. Bei Fehler: sofort Rollback, Stufe stoppen.
- **Single Source of Truth gilt ab M0:** Router-Änderungen nur über Admin-DB/Admin-API, nie YAML.
- **Abbruch-Kriterium je Stufe:** wenn die Verifikation rot ist → Rollback, nicht „weiterdrücken".
- **🏭 CCX23 = PRODUKTION** (workshop.flowaudit.de, checklist/audit_designer-Prod, cockpit, llm-router). **Alle Eingriffe/Redeploys auf Hetzner/CCX23 kommen ZULETZT** (eigene Schluss-Stufe), off-peak, einzeln, mit Smoke nach jedem Schritt. Vorher: NUC + evo-x2 + reine Repo-/Code-Vorbereitung.
- **Hinweis Abhängigkeit:** Die Prod (CCX23-Workshop) hängt an NUC-ai-router (Knowledge) + evo-x2 (Modelle). NUC-/evo-Schritte sind daher zwar „nicht auf Hetzner", können aber die Prod-RAG/LLM kurz beeinflussen → ebenfalls off-peak + sofort verifizieren.
- **🧪 NUC/lokal ist der Beweis-Boden:** Jede Maßnahme, die später auch CCX23 betrifft, wird **zuerst auf NUC/lokal umgesetzt UND verifiziert**. CCX23 erhält in der Schluss-Stufe nur Änderungen, die lokal nachweislich funktioniert haben — **1:1 repliziert**, keine Experimente auf der Produktion. Klappt etwas lokal nicht → wird CCX23 gar nicht erst angefasst.
- **⚠️ NUC ist KEIN harmloser Beweis-Boden (Codex):** Die Prod-RAG nutzt `NUC:7849` und evo-x2 als einzigen LLM-Backend. NUC-/evo-Schritte sind daher **produktionsrelevant** zu behandeln (Prod-Grade-Backup + RAG-Referenzfragen vor/nach + konkrete Rollback-Kommandos), nicht „nur lokal".
- **📏 Messbare Gates (nicht nur „Smoke grün", Codex):** Pass-Kriterium je Gate = 24/24 Smoke **UND** 5xx=0 in den Logs **UND** RAG-Referenzfragen liefern stabile Treffer **UND** LLM-Latenz/Timeouts im Rahmen (p95) **UND** Router-Routen aus Admin-DB korrekt **UND** keine unerwartete Health-Degradation. Vorher 3–5 RAG-Referenzfragen + erwartete LLM-Latenz festlegen.
- **🧰 Rollback braucht ARTEFAKTE, nicht nur Absicht (Codex):** je Schritt vorab sichern — Admin-DB **inkl. WAL/SHM** (konsistent), Compose-Dateien, `.env`/Secrets-Referenzen, systemd-Units, Volumes/Uploads, **aktuelle Image-Digests** (GHCR-Tags allein reichen nicht).

---

## STUFE 0 — Pre-Flight (PFLICHT-GATE, vor allem anderen)
**Ziel: sicherstellen, dass Tokens, SSH und Tailscale wirklich funktionieren — sonst scheitert jede spätere Stufe mitten im Lauf.**
Nichts wird geändert; nur getestet. Erst wenn ALLES grün → Stufe 1 freigeben.

### ✅ Stufe-0-Ergebnis (ausgeführt 2026-05-27, read-only)
- **0.1 Tailscale:** ✅ NUC + CCX23 (23 ms) + evo2 (1 ms) active. (macbook offline = schläft, egal.)
- **0.2 SSH+sudo:** NUC lokal ✓ · CCX23 ssh+`sudo -n` ✓ · evo-x2 ssh ✓ · **evo-x2 `sudo -n` ✓ (2026-05-27 eingerichtet: `/etc/sudoers.d/90-janpow-nopasswd`, visudo-validiert)** — M11c-Blocker behoben.
- **0.3 GitHub/GHCR:** ✅ gh-Token lebt (rate_limit 5000), Scopes inkl. `write:packages`; GHCR-Pull ok, Push diese Session bewiesen. cockpit hat **kein** `GITHUB_TOKEN` in /etc (GitHub-View optional; kein verstreuter PAT — gut).
- **0.4 Cloudflare:** ✅ Tunnel up (checklist 9 d + nuc/audit_designer/kira), Domains 200. **Kein zentraler CF-API-Token** (nur per-Tunnel-Run-Tokens) → M16 kleiner als gedacht.
- **0.5 Hetzner:** ✅ SSH/deploy funktioniert. **Kein hcloud-API-Token** (Zugang = SSH) → M16 kleiner.
- **0.6 Backups:** ✅ NUC-Backup-Skript+Log vorhanden; ai-router admin.db (NUC+CCX23) vorhanden & kopierbar. (Voller Artefakt-Snapshot je Schritt erst zur Ausführung.)
- **GATE-0-Verdikt:** 🟢 **vollständig grün** — evo-x2-sudo nachgerüstet. Stufe 1 freigebbar.
- **Token-Konsequenz für M16:** Umfang schrumpft — zentralisieren betrifft praktisch nur die **GitHub/GHCR**-Credential (gh-Keyring + docker-config). Cloudflare = per-Tunnel (bleibt), Hetzner = SSH (kein API-Token).

### 0.1 Tailscale-Erreichbarkeit (alle Hosts)
- [ ] `tailscale status` → NUC, CCX23 (100.99.159.80), evo-x2 (100.81.4.99) **online/active**. (macbook darf offline sein.)
- [ ] Ping/Probe: `tailscale ping cockpit-nbg1-1` , `tailscale ping evo2`.
- Pass: alle 3 Hosts erreichbar, keine DNS-Health-Blocker.
- *Vorab-Stand:* NUC/CCX23/evo2 erreichbar ✓; 1 DNS-Health-Warnung auf NUC (prüfen, ob relevant).

### 0.2 SSH (alle Hosts, non-interaktiv)
- [ ] NUC: lokal (kein SSH). ✓
- [ ] CCX23: `ssh -o BatchMode=yes deploy@cockpit-nbg1-1.tailec75b1.ts.net true` → Exit 0. ✓ (verifiziert)
- [ ] evo-x2: `ssh -o BatchMode=yes janpow@100.81.4.99 true` → Exit 0. ✓ (verifiziert)
- [ ] **sudo** auf CCX23 + evo-x2 ohne Passwort (für compose/systemd): `ssh … sudo -n true`. (CCX23 ✓)
- Pass: passwortloser SSH + sudo auf allen Zielhosts.

### 0.3 GitHub / GHCR-Token
- [ ] `gh auth status` → eingeloggt `janpow77`, Scopes enthalten `write:packages`, `repo`, `read:org`. (✓)
- [ ] Token lebt: `gh api rate_limit` → 200.
- [ ] GHCR-Push-Fähigkeit: `docker login ghcr.io` Status / Testtag push in ein Wegwerf-Repo ODER `docker pull ghcr.io/janpow77/<image>:latest` (Pull beweist Read).
- [ ] **Ablaufdatum** des PAT prüfen (Classic vs Fine-grained). cockpit-`GITHUB_TOKEN` separat validieren (`curl -H "Authorization: token …" https://api.github.com/rate_limit`).
- Pass: GHCR Pull **und** Push gehen; Token nicht kurz vor Ablauf.

### 0.4 Cloudflare-Token
- [ ] **Tunnel-Run-Tokens** (per App): Tunnel laufen? `docker ps | grep cloudflared` → alle Up. (checklist 9d, audit_designer/nuc/kira ✓)
- [ ] **Cloudflare-API-Token** (für DNS/Tunnel-Mgmt, falls genutzt): `curl -H "Authorization: Bearer <CF_API>" https://api.cloudflare.com/client/v4/user/tokens/verify` → `"status":"active"`.
- [ ] Öffentliche Erreichbarkeit live: `curl -I https://workshop.flowaudit.de` + checklist-Domain → 200/redirect.
- Pass: Tunnel up + (falls API-Token existiert) `verify` aktiv.

### 0.5 Hetzner-Token
- [ ] **Deploy-SSH** (s. 0.2) = der praktisch genutzte Weg. ✓
- [ ] **hcloud-API-Token** (falls vorhanden/genutzt): `hcloud server list` bzw. `curl -H "Authorization: Bearer <HCLOUD>" https://api.hetzner.cloud/v1/servers` → 200. Sonst: „nicht genutzt" dokumentieren.
- Pass: der tatsächlich genutzte Hetzner-Zugang funktioniert.

### 0.6 Backups & Rollback-Artefakte (Codex: Artefakte, nicht nur Absicht)
- [ ] NUC-Backup-Cron läuft (`backup-to-gdrive.sh` 03:00). ✓
- [ ] **ai-router Admin-DB-Backup konsistent** (NUC + CCX23) — **inkl. WAL/SHM**: vor `cp` `PRAGMA wal_checkpoint(TRUNCATE)` bzw. Router kurz stoppen, dann `admin.db`+`-wal`+`-shm` sichern. `…bak-<host>-<datum>`.
- [ ] DB-Dumps audit_designer (NUC `audit_designer` + CCX23 `checklist`) vor Schema-/app_id-Schritten.
- [ ] **Artefakt-Snapshot je betroffenem Dienst:** Compose-Datei(en), `.env`/Secrets-Referenzen, systemd-Units (evo), Volumes/Uploads-Liste, **aktuelle Image-Digests** (`docker inspect --format '{{.Image}}'`).
- [ ] **RAG-Referenzfragen** (3–5) + erwartete Treffer festhalten (Vorher-Baseline für die Gate-Prüfung).
- [ ] **manueller cockpit-Fallback** notiert (Compose + Image-Digest), falls `deploy_app` selbst fehlschlägt.
- Pass: frische, konsistente Backups + Artefakte + Restore-Kommandos je Schritt notiert.

**GATE 0 → 1:** Alle 0.1–0.6 grün. Sonst zuerst den roten Punkt fixen (z. B. abgelaufenen Token erneuern), bevor irgendeine Maßnahme startet.

---

> **Sequenzierung nach Host: erst Repo-Vorbereitung → dann NUC/evo-x2 → CCX23/Produktion ZULETZT.**

## STUFE 1 — 🟢 Repo-/Code-Vorbereitung (KEIN Deploy auf laufende Dienste)
**Zeitbudget: ~1–2 h.** Reversibel, kein Live-Eingriff.
- Alle Code-/Doc-/Skript-Änderungen je Repo auf Feature-Branches committen (cockpit `deploy_app` ordnen, bootstrap-Erweiterung, M0-Skripte, spoke-widget-Port).
- Images, die später gebraucht werden, **lokal** bauen+pushen (`ghcr-build-push.sh`) — Build ≠ Deploy.
- M0 Schritt 1 — `dump_admin_config.py` (Export beider Admin-DBs, versioniert) — reiner Read.
- **Verifikation:** Branches/Images vorhanden; Export eingecheckt; nichts Laufendes verändert.
- **GATE 1 → 2:** Smoke 24/24 unverändert grün.

> **✅ Stufe 2 (2026-05-27) — Kern abgeschlossen:** Backups NUC-admin.db ✓ · **M14 ✓** (tote Spokes disabled, kein Restart) · **M2 analysiert** (default = bge-m3-Embeddings) · **M11c ✓ obsolet** (evo-ollama ist bereits getunter Docker-Container, kein Restart nötig — war Misread) · **F17 ✓** (NUC-Admin-PW via .env erzwungen, admin/admin geschlossen, Router recreated+verifiziert, Prod grün; PW in `ai-router/.env` gitignored). **Offen (gering/Stage-3):** M2-Fix (Embedder labeln, App-Restart, niedrig); **F17 für CCX23-Router** (gleiches admin/admin — Stage 3); evo-health-monitor (minor).

## STUFE 2 — 🟡 NUC + evo-x2 (Backend-Hosts, off-peak, je Schritt verifizieren)
**Zeitbudget: ~3–5 h.** Backup der NUC-Admin-DB + DB-Dumps vor Start (0.6). NICHT auf CCX23.
- M14 — tote Spokes (`nuc-/evo-gpu-llm-manager`) aus **NUC**-admin_spokes entfernen.
- M0 (NUC-Router) — Admin-DB als SoT auf der NUC, YAML als „nicht live" kennzeichnen, Drift-Check.
- M2 (NUC-Consumer) — `default`-Traffic-Quelle identifizieren → NUC-Consumer registrieren/labeln (audit_designer-NUC, krypto, love-ai sind bereits ok; regulierung/flowaudit falls NUC-Router-Consumer).
- M3/M6 (NUC-seitig) — Modell-Tags der NUC-Consumer auf servierte Tags.
- M11c — **evo-x2** ollama in systemd-Unit + Concurrency explizit; `evo-health-monitor` reparieren. (Primärer Single-LLM-Backend!) **Vorab definieren (Codex):** Stop/Start-Wartungsfenster, erwartete Modell-Ladezeiten, **Fallback auf alten bare-root-Prozess**, p95-/Timeout-Grenzen, Smoke mit **echten Prod-Prompts**. Fallback-Spoke nuc-ollama prüfen.
- M16b — evo-x2 `llama-update.timer`-Policy.
- **Verifikation (messbar):** NUC-Router-Routen aus Admin-DB korrekt; evo ollama:11434 serviert alle Modelle + Auto-Restart getestet; **RAG-Referenzfragen stabil** (vs. 0.6-Baseline); LLM-Latenz p95 im Rahmen; **Prod-Workshop-Smoke 24/24 + 5xx=0** (Prod hängt an NUC-RAG + evo).
- **Rollback:** NUC-Admin-DB (inkl. WAL) aus Backup + Router-Restart; evo systemd-Unit entfernen → bare-Prozess reaktivieren.
- **GATE 2 → 3:** LLM über alle Apps grün; Prod unbeeinträchtigt.

> **✅ Stufe 3 (2026-05-27) — Kern erledigt:** CCX23-admin.db gesichert · **F17-CCX23 = nicht nötig** (PW bereits gesetzt, admin→401) · bootstrap llm-router-Pfad gefixt (/opt/ai-router) · **cockpit-Redeploy ✓** (cockpit:v0.2 gebaut→transferiert→recreated, healthy; **deploy_app live**, 5 Monitoring-Apps angelegt; Rollback cockpit:v0.1 + compose-Backup vorhanden) · Prod (workshop/checklist) unberührt. **Offen (gering, optional):** M2-Fix (Embedder labeln), M9 (app_id-Drift, kosmetisch/riskant), M16 (Token minimal), CCX23-admin.db-Bloat-Cleanup (~60 MB audit). qwen2.5-Route ungenutzt (egal).

## STUFE 3 — 🏭🔴 CCX23 / Hetzner = PRODUKTION (ZULETZT, einzeln, Backup+Rollback je Schritt, off-peak)
**Zeitbudget: ~3–5 h, gepuffert.** Erst wenn NUC/evo grün. **Repliziert die in Stufe 2 lokal bewiesenen Änderungen 1:1 — keine neuen Experimente auf Prod.** **Nach JEDEM Schritt Prod-Smoke (24/24).**
- M17 — CCX23 Prune-Cron einrichten — **Dry-Run zuerst + konservative Retention** (Codex); Einmal-Prune lief bereits, kein Container-Neustart.
- M0 (CCX23-Router) — Admin-DB als SoT auf CCX23, NUC↔CCX23-Routen abgleichen. (Bedient die Prod-Workshop-LLM → konsistentes Backup inkl. WAL + 1 Route testen.)
- M3/M6 (Workshop/checklist) — Prod-Modell-Tags auf servierte Tags.
- M16/M13 — **Token/Secrets** in cockpit-Vault zentralisieren (scoped) — **Parallelbetrieb + Env-Diff** (Codex: alt+neu nebeneinander, vergleichen, dann umschalten). **Tunnel-Run-Tokens NICHT anfassen** (sonst workshop.flowaudit.de offline).
- M9 — app_id `checklist`↔`audit_designer` vereinheitlichen. **Vorsicht (Codex):** kann Historie/Audit-Daten/Sessions/Router-Mappings brechen → Impact prüfen, ggf. nur additiv registrieren statt umbenennen.
- **cockpit-Redeploy** — `deploy_app` ausrollen, **als allerletztes**. **Manueller Fallback Pflicht (Codex):** Compose + Image-Digest, da `deploy_app` neu/unbewährt ist und nicht der einzige Rettungsweg sein darf.
- **Verifikation je Schritt (messbar):** Prod-Smoke 24/24 + 5xx=0; GHCR Pull/Push; Tunnel up + Domains 200; RAG-Referenzfragen stabil; LLM via CCX23-Router + Latenz ok.
- **Rollback je Schritt:** Admin-DB(+WAL)/Image-Digest/Token/env zurück; Tunnel niemals ohne sofortigen Rückweg ändern.
- **GATE 3 → 4:** alles grün + 24 h beobachtet.

## STUFE 4 — Ausbau (nach sauberer Basis)
- M10 — nur falls nötig (qchess existiert live nicht → entfällt vermutlich; **kb_chunks NICHT neu einbetten**).
- M12 — Compose-Hygiene (kanonische Datei je Repo kennzeichnen).
- M18 — Overview-Widget (read-only) auf cockpit+ai-router-APIs + Deep-Links. **Erst jetzt.**

---

## Offene Entscheidungen (vor Stufe 2/3 zu klären)
1. M0: YAML stilllegen vs. Re-Seed-Skript.
2. app_id vereinheitlichen + bleibt die NUC-audit_designer-Instanz dauerhaft?
3. Token-Scoping + wer materialisiert Vault → `/etc/<app>/env`.
4. Re-Embed-Umfang (Default: keiner).

## Zeit-Gesamtbild
Stufe 0: ~1 h · Stufe 1: 1–2 h · Stufe 2: 2–4 h · Stufe 3: 3–5 h · Stufe 4: nach Bedarf.
→ **Realistisch ein Wartungsfenster über mehrere Sitzungen**, nicht ein Sprint. Stufe 0 kann jederzeit vorab laufen (read-only).
