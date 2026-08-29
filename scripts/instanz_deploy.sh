#!/usr/bin/env bash
# Cockpit-Instanz auf einem Linux-Host anlegen oder aktualisieren (Tailscale-only, Host-Netz).
#
#   scripts/instanz_deploy.sh <selfhost> <image-tag> [instanzverzeichnis]
#   z. B.  scripts/instanz_deploy.sh nuc v0.3.7
#          scripts/instanz_deploy.sh janpow-ai v0.3.7
#
# Voraussetzungen auf dem Host: Docker + Compose-Plugin, Tailscale, das Image cockpit:<tag>
# (lokal gebaut oder per `docker save | ssh host docker load` uebertragen), ~/.ssh/id_ed25519
# als Schluessel zu den anderen Hosts. Optional in der Umgebung: GITHUB_TOKEN, AI_ROUTER_URL,
# COCKPIT_BACKUP_DIR (Sicherungsverzeichnis fuer die Wand-Kachel).
#
# Legt an (einmalig, wird bei spaeteren Laeufen nicht ueberschrieben): env (Admin-Passwort und
# Vault-Schluessel), config.yaml (Hosts der Landschaft, Self-Host = <selfhost>), .admin_pw.
# Schreibt bei jedem Lauf neu: compose.yaml, .env (Image-Tag, Bind-IP). Dann `docker compose up -d`.
set -euo pipefail

SELF="${1:?Self-Host-Name, z. B. nuc | janpow-ai | evo}"
TAG="${2:?Image-Tag, z. B. v0.3.7}"
DIR="${3:-$HOME/cockpit-instanz}"
PORT="${COCKPIT_PORT:-7843}"

command -v docker >/dev/null || { echo "docker fehlt"; exit 1; }
docker compose version >/dev/null 2>&1 || { echo "docker compose (Plugin) fehlt"; exit 1; }
docker image inspect "cockpit:$TAG" >/dev/null 2>&1 || { echo "Image cockpit:$TAG fehlt – erst bauen oder per docker load laden"; exit 1; }
TS_IP="$(tailscale ip -4 2>/dev/null | head -1 || true)"
[ -n "$TS_IP" ] || { echo "Tailscale-IP nicht ermittelbar (tailscale ip -4)"; exit 1; }
[ -f "$HOME/.ssh/id_ed25519" ] || echo "Hinweis: $HOME/.ssh/id_ed25519 fehlt – andere Hosts sind dann nicht per SSH erreichbar"

mkdir -p "$DIR/data" "$DIR/backups"
chmod 700 "$DIR"

# --- env: Zugangsdaten nur einmal erzeugen -----------------------------------
if [ ! -f "$DIR/env" ]; then
  PW="$(openssl rand -base64 21 | tr -d '/+=' | cut -c1-22)"
  VK="$(openssl rand 32 | base64 | tr '+/' '-_')"   # Fernet: 32 Byte, url-safe base64
  umask 077
  cat > "$DIR/env" <<EOF
COCKPIT_ADMIN_USER=admin
COCKPIT_ADMIN_PASSWORD=$PW
COCKPIT_VAULT_KEY=$VK
COCKPIT_SELF_HOST=$SELF
COCKPIT_CONFIG=/etc/cockpit/config.yaml
ADMIN_DB_PATH=/data/cockpit.db
COCKPIT_DATA_DIR=/data
COCKPIT_PORT=$PORT
EOF
  printf '%s' "$PW" > "$DIR/.admin_pw"
  echo "Zugangsdaten erzeugt: Benutzer admin, Passwort in $DIR/.admin_pw"
fi
# optionale Werte nachziehen, ohne vorhandene zu ueberschreiben
GH="${GITHUB_TOKEN:-$(gh auth token 2>/dev/null || true)}"
if [ -n "$GH" ] && ! grep -q '^GITHUB_TOKEN=' "$DIR/env"; then printf 'GITHUB_TOKEN=%s\n' "$GH" >> "$DIR/env"; echo "GITHUB_TOKEN eingetragen"; fi
if [ -n "${AI_ROUTER_URL:-}" ] && ! grep -q '^AI_ROUTER_URL=' "$DIR/env"; then printf 'AI_ROUTER_URL=%s\n' "$AI_ROUTER_URL" >> "$DIR/env"; echo "AI_ROUTER_URL=$AI_ROUTER_URL eingetragen"; fi

# --- config.yaml: Landschaft (Bootstrap, danach Host-Verwaltung im Cockpit) --
if [ ! -f "$DIR/config.yaml" ]; then
  self_flag() { [ "$1" = "$SELF" ] && echo true || echo false; }
  cat > "$DIR/config.yaml" <<EOF
# Bootstrap-Hosts dieser Cockpit-Instanz (Self-Host: $SELF). Aenderungen danach im Cockpit unter Hosts.
hosts:
  - name: ccx23
    tailscale_ip: 100.99.159.80
    ssh_user: deploy
    ssh_key_path: /root/.ssh/cockpit_id_ed25519
    description: "Hetzner CCX23 — Prod (HPP, Checklist, flowinvoice, Workshop, ai-router)"
    is_self: $(self_flag ccx23)
  - name: nuc
    tailscale_ip: 100.102.132.11
    ssh_user: janpow
    ssh_key_path: /root/.ssh/cockpit_id_ed25519
    description: "NUC — Entwicklung, Harvesting, Kira-RAG"
    is_self: $(self_flag nuc)
  - name: evo
    tailscale_ip: 100.81.4.99
    ssh_user: janpow
    ssh_key_path: /root/.ssh/cockpit_id_ed25519
    description: "EVO-X2 — Multi-GPU, ai-router-Spoke"
    is_self: $(self_flag evo)
  - name: janpow-ai
    tailscale_ip: 100.114.73.106
    ssh_user: janpow
    ssh_key_path: /root/.ssh/cockpit_id_ed25519
    description: "janpow-ai — KI-Rechner"
    is_self: $(self_flag janpow-ai)
  - name: macbook-air
    tailscale_ip: 100.70.245.26
    ssh_user: janriener
    ssh_key_path: /root/.ssh/cockpit_id_ed25519
    description: "MacBook Air — Vorführrechner"
    is_self: $(self_flag macbook-air)
EOF
fi

# --- compose: Host-Netz, Bind nur auf die Tailscale-IP ------------------------
cat > "$DIR/.env" <<EOF
COCKPIT_IMAGE_TAG=$TAG
COCKPIT_BIND_IP=$TS_IP
COCKPIT_PORT=$PORT
HOME_DIR=$HOME
BACKUP_DIR=${COCKPIT_BACKUP_DIR:-$DIR/backups}
EOF
cat > "$DIR/compose.yaml" <<'EOF'
# Cockpit-Instanz (erzeugt von scripts/instanz_deploy.sh). Host-Netz, damit Dienste auf
# 127.0.0.1 des Hosts (Memory-API, ai-router-Hub) erreichbar sind; gebunden nur an die Tailscale-IP.
services:
  cockpit:
    image: cockpit:${COCKPIT_IMAGE_TAG}
    container_name: cockpit
    restart: unless-stopped
    network_mode: host
    env_file:
      - ./env
    command: ["uvicorn", "cockpit.main:app", "--host", "${COCKPIT_BIND_IP}", "--port", "${COCKPIT_PORT}", "--workers", "1"]
    volumes:
      - ./data:/data
      - ./config.yaml:/etc/cockpit/config.yaml:ro
      - ${HOME_DIR}/.ssh/id_ed25519:/root/.ssh/cockpit_id_ed25519:ro
      - /var/run/docker.sock:/var/run/docker.sock
      # Werkstatt und Kira (.env von audit_designer) - gleicher Pfad wie auf dem Host, nur lesend
      - ${HOME_DIR}/Projekte:${HOME_DIR}/Projekte:ro
      - ${BACKUP_DIR}:/backups:ro
    healthcheck:
      test: ["CMD", "curl", "-fsS", "http://${COCKPIT_BIND_IP}:${COCKPIT_PORT}/health"]
      interval: 30s
      timeout: 5s
      retries: 3
      start_period: 10s
    mem_limit: 512M
    logging:
      driver: json-file
      options:
        max-size: "10m"
        max-file: "3"
EOF

(cd "$DIR" && docker compose up -d)
for _ in $(seq 1 30); do
  if curl -fsS -m 3 "http://$TS_IP:$PORT/health" >/dev/null 2>&1; then
    echo "Cockpit laeuft: http://$TS_IP:$PORT/admin/board  (Benutzer admin, Passwort: $DIR/.admin_pw)"
    exit 0
  fi
  sleep 2
done
echo "Cockpit antwortet nicht – docker logs cockpit pruefen"; exit 1
