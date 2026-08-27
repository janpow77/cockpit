#!/usr/bin/env bash
# Kopiert Vault-Secrets vom Hetzner-Cockpit (Quelle) in eine andere Cockpit-Instanz (Ziel).
#
#   scripts/instanz_secrets_sync.sh <ziel-url> <ziel-admin-pw-datei> [schluessel ...]
#   z. B. scripts/instanz_secrets_sync.sh http://100.102.132.11:7843 ~/cockpit-instanz/.admin_pw
#
# Die Werte werden auf dem Hetzner serverseitig aus dem Vault gelesen (Login mit dem dortigen
# Passwort aus /etc/cockpit/env), als JSON ueber die SSH-Verbindung an dieses Skript gereicht und
# direkt in den Ziel-Vault geschrieben (POST/PATCH /admin/api/secrets). Nichts landet auf Platte,
# nichts wird ausgegeben – nur Schluesselnamen und HTTP-Codes.
set -euo pipefail

ZIEL="${1:?Ziel-URL, z. B. http://100.102.132.11:7843}"
PWFILE="${2:?Datei mit dem Admin-Passwort der Ziel-Instanz}"
shift 2
KEYS=("$@")
[ ${#KEYS[@]} -gt 0 ] || KEYS=(hpp_demo_user hpp_demo_password hpp_smoke_user hpp_smoke_password mcp_flowaudit_token)
QUELLE_SSH="${QUELLE_SSH:-hetzner}"
QUELLE_URL="${QUELLE_URL:-http://100.99.159.80:7843}"

# Exporthelfer auf die Quelle bringen (kein Heredoc ueber ssh, daher Datei per scp)
TMP="$(mktemp)"
cat > "$TMP" <<'EOF'
#!/usr/bin/env bash
set -u
BASE="$1"; shift
PW=$(sudo sed -n 's/^COCKPIT_ADMIN_PASSWORD=//p' /etc/cockpit/env | head -1 | tr -d '"\r')
TOKEN=$(curl -s -m 10 -H 'Content-Type: application/json' -d "{\"username\":\"admin\",\"password\":\"$PW\"}" "$BASE/admin/api/auth/login" | python3 -c 'import sys,json; print(json.load(sys.stdin).get("token",""))')
[ -n "$TOKEN" ] || { echo '{}' ; exit 1; }
python3 - "$BASE" "$TOKEN" "$@" <<'PY'
import json, sys, urllib.request
base, token, *keys = sys.argv[1:]
hdr = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
def call(method, path, body=None):
    req = urllib.request.Request(base + path, data=json.dumps(body).encode() if body is not None else None, headers=hdr, method=method)
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read() or b"null")
vorhanden = {s["key"]: s["id"] for s in call("GET", "/admin/api/secrets")}
out = {}
for k in keys:
    if k in vorhanden:
        out[k] = call("POST", f"/admin/api/secrets/{vorhanden[k]}/reveal", {"purpose": "Abgleich in weitere Cockpit-Instanz"}).get("value")
print(json.dumps(out))
PY
EOF
scp -q "$TMP" "$QUELLE_SSH:/tmp/.cockpit_secrets_export.sh"
rm -f "$TMP"
JSON="$(ssh "$QUELLE_SSH" "bash /tmp/.cockpit_secrets_export.sh '$QUELLE_URL' ${KEYS[*]}; rm -f /tmp/.cockpit_secrets_export.sh")"

ZIEL_PW="$(tr -d '\n\r' < "$PWFILE")"
printf '%s' "$JSON" | python3 - "$ZIEL" "$ZIEL_PW" <<'PY'
import json, sys, urllib.request
ziel, pw = sys.argv[1:3]
werte = json.load(sys.stdin)
def call(method, path, body=None, token=None):
    hdr = {"Content-Type": "application/json"}
    if token: hdr["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(ziel + path, data=json.dumps(body).encode() if body is not None else None, headers=hdr, method=method)
    with urllib.request.urlopen(req, timeout=15) as r:
        return r.status, json.loads(r.read() or b"null")
_, login = call("POST", "/admin/api/auth/login", {"username": "admin", "password": pw})
token = login["token"]
_, vorhanden = call("GET", "/admin/api/secrets", token=token)
ids = {s["key"]: s["id"] for s in vorhanden}
for k, v in werte.items():
    if not v:
        print(f"  {k}: in der Quelle nicht vorhanden – uebersprungen"); continue
    if k in ids:
        st, _ = call("PATCH", f"/admin/api/secrets/{ids[k]}", {"value": v, "comment": "aus dem Hetzner-Cockpit abgeglichen"}, token=token)
        print(f"  {k}: aktualisiert (HTTP {st})")
    else:
        st, _ = call("POST", "/admin/api/secrets", {"key": k, "value": v, "app_tag": "wand", "comment": "aus dem Hetzner-Cockpit abgeglichen"}, token=token)
        print(f"  {k}: angelegt (HTTP {st})")
PY
