# Tailscale-Fallback ueber Cloudflare-Tunnel

Stand: 2026-05-11
Geltungsbereich: NUC-ML-Services (`ollama`, `reranker-service`, kuenftig
`vision-service`), Konsument `llm-router` auf CCX23.

## TL;DR

Primaerpfad CCX23 → NUC ist Tailscale (`100.102.132.11`). Bei Ausfall
springt der `llm-router` auf `https://<service>-nuc.flowaudit.de`, einen
durch Cloudflare-Access geschuetzten Tunnel auf der NUC. Der Failover
ist im Cockpit-Audit-Tab als Action `route.failover` sichtbar.

## Architektur

```
                   ┌──────────────────────────────────────────────────┐
                   │  CCX23 (Hetzner, Nuernberg)                       │
                   │  ┌──────────────────────────────────────────┐    │
   Workshop / ───▶ │  │  llm-router :7842                         │    │
   audit_designer  │  │  ENV: CF_ACCESS_CLIENT_ID/SECRET          │    │
                   │  └────────────────┬─────────────────────────┘    │
                   └────────────────────┼─────────────────────────────┘
                                        │
                  ┌─── primary path ───┴──── fallback path ─────┐
                  │                                              │
                  ▼ Tailscale-WireGuard                          ▼ Cloudflare-Edge (Frankfurt)
   ┌──────────────────────────────┐         ┌──────────────────────────────────────┐
   │ 100.102.132.11 (NUC)         │         │ https://*-nuc.flowaudit.de            │
   │ TCP 11434 (ollama)           │         │ Cloudflare-Access: Service-Auth        │
   │ TCP 8004  (reranker-service) │         │ Token: CF-Access-Client-Id/Secret      │
   │ TCP 8005  (vision-service)   │         └──────────────┬───────────────────────┘
   └──────────────────────────────┘                        │
                                                            ▼ Cloudflare-Tunnel (cloudflared:host)
                                          ┌──────────────────────────────┐
                                          │ NUC (network_mode: host)      │
                                          │ -> 127.0.0.1:11434/8004/8005  │
                                          └──────────────────────────────┘

Wechsel-Trigger (im Router):
  - 3x in Folge TCP-Connect-Timeout/Refused auf base_url, ODER
  - 3x in Folge HTTP-5xx auf base_url
Wechsel-Dauer:
  - Sliding window 5 Minuten: nach 5 Minuten ohne Fehler ruecksprung auf Tailscale.

Sicherheit:
  - Service-Token rotiert jaehrlich (siehe llm-router/docs/fallback-cloudflare.md).
  - Ohne Token: Cloudflare-Access antwortet mit 302 -> idp.cloudflare.com (kein Datenleck).
  - Token-Header werden nur fuer Hostnames mit "*-nuc.flowaudit.de"-Pattern gesetzt
    (Defense in depth, nicht zwingend).
```

## Test-Befehle

### 1) Primary-Pfad gesund

```bash
# Auf CCX23
curl -s -H "X-App-Id: audit_designer" http://localhost:7842/api/tags | jq '.models | length'
# Erwartet: Anzahl Modelle (z.B. 8). Header X-Llm-Failover NICHT gesetzt.
```

### 2) Failover-Provokation

```bash
# Auf NUC: Tailscale stoppen
sudo tailscale down

# Auf CCX23: einen Embedding-Call schicken (reproduzierbar fuer Reranker)
curl -i -X POST http://localhost:7842/v1/rerank \
  -H "X-App-Id: audit_designer" \
  -H "Content-Type: application/json" \
  -d '{"model":"bge-reranker-v2-m3","query":"test","documents":["a","b"]}'

# Erwartet im Response-Header:
#   X-Llm-Failover: 1
#   X-Llm-Spoke: nuc-reranker
# HTTP-Status: 200
```

### 3) Cloudflare-Access verifizieren (negativ)

```bash
# Ohne Service-Token muss Cloudflare ablehnen
curl -i https://reranker-nuc.flowaudit.de/health
# Erwartet: HTTP/2 302 zu cloudflareaccess.com   (oder 401)

# Mit Token:
curl -i https://reranker-nuc.flowaudit.de/health \
  -H "CF-Access-Client-Id: ${CF_ACCESS_CLIENT_ID}" \
  -H "CF-Access-Client-Secret: ${CF_ACCESS_CLIENT_SECRET}"
# Erwartet: HTTP/2 200 + JSON
```

### 4) Restore Primary

```bash
# Auf NUC
sudo tailscale up
# Auf CCX23: ein paar Requests schicken — Router fuehrt einen Probe-Request
# auf base_url aus und schaltet zurueck, sobald base_url 3x 200 liefert.
```

## Monitoring im Cockpit

Cockpit liest die `admin_audit`-Tabelle des llm-router (SQLite,
`/data/admin.db`) ueber den Cockpit-Service `audit_stream` (auf der Roadmap).
Bis dahin:

### Manueller Check (heute schon moeglich)

```bash
# Auf CCX23
docker exec llm-router sqlite3 /data/admin.db \
  "SELECT ts, actor, action, target, before, after \
   FROM admin_audit \
   WHERE action='route.failover' \
   ORDER BY ts DESC LIMIT 20;"
```

### Cockpit-Audit-Tab (zukuenftig)

Sobald der llm-router den Audit-Event `route.failover` emittiert (siehe
`llm-router/docs/fallback-patch.diff`), erscheint im Cockpit unter
`Apps -> llm-router -> Audit` eine Zeile:

```
2026-05-11 14:32:08  router    route.failover    nuc-reranker
  before: http://100.102.132.11:8004
  after : https://reranker-nuc.flowaudit.de
```

Alerting (optional): im Cockpit `Alerts`-Tab eine Regel
`action == "route.failover" AND count > 3 / 1h -> notify-jan`
hinterlegen, damit haeufige Failover-Bursts (= Tailscale-Wackler) gemeldet
werden, statt unbemerkt zu bleiben.

## Bekannte Fallstricke

- **`Ollama` auf NUC hoert default nur auf `127.0.0.1`**: bestehender
  Tailscale-Pfad funktioniert, weil `OLLAMA_HOST=0.0.0.0` in der ollama-
  systemd-Unit gesetzt ist. Der cloudflared-Container nutzt `network_mode:
  host` und erreicht damit `127.0.0.1:11434` direkt — kein extra Konfig
  noetig.
- **`reranker-service`** lauscht auf `0.0.0.0:8004`. Wenn das aus Sicherheits-
  gruenden auf `127.0.0.1` geaendert wird, weiterhin OK — Tunnel nutzt
  Host-Network.
- **TLS-Termination**: Cloudflare-Edge macht TLS, der Tunnel zur NUC ist
  intern (kein TLS). `noTLSVerify=true` in der Cloudflare-Public-Hostname-
  Config ist Pflicht.
- **WebSocket-Streaming**: cloudflared unterstuetzt das transparent.
  Ollama-Streaming (`/api/generate` mit `stream:true`) wurde mit dem
  bestehenden audit_designer-Tunnel verifiziert.
- **Latenz**: Tailscale-WireGuard ~3-6 ms (CCX23<->NUC ueber DTAG). Cloudflare-
  Tunnel ~12-30 ms (CCX23<->Cloudflare-Frankfurt<->NUC). Fuer Embeddings/Rerank
  unkritisch, aber sichtbar bei kleinen Prompts.
- **Token-Rotation**: nicht vergessen. Service-Token ohne Expiry == ewige
  Erblast. 12-Monats-Reminder im Cockpit-Backlog.

## Querverweise

- `llm-router/docs/fallback-cloudflare.md` — Cloudflare-UI-Schritte
- `llm-router/docs/nuc-cloudflared-fallback.compose.yaml` — Compose-Snippet NUC
- `llm-router/docs/fallback-patch.diff` — Code-Patch fuer Header-Injection
- `Workshop/HETZNER_MIGRATION_STATUS.md` — Tailscale-Hintergrund
