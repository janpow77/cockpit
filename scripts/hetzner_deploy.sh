#!/usr/bin/env bash
# Cockpit auf den Hetzner bringen (ein Befehl statt fuenf Schritte):
#   scripts/hetzner_deploy.sh [tag]        Vorgabe: Version aus pyproject.toml, z. B. v0.3.15
# Ablauf: Image lokal bauen -> per SSH laden -> compose.yaml einspielen -> Container neu starten
#         -> Health pruefen -> alte Images auf beiden Seiten aufraeumen -> Smoketest.
set -euo pipefail
cd "$(dirname "$0")/.."
TAG="${1:-v$(sed -n 's/^version = "\(.*\)"/\1/p' pyproject.toml | head -1)}"
HOST="${COCKPIT_SSH_HOST:-hetzner}"
URL="${COCKPIT_URL:-http://100.99.159.80:7843}"
PWFILE="${COCKPIT_PW_FILE:-$HOME/.cockpit_admin_pw}"

grep -q "image: cockpit:$TAG" compose.yaml || sed -i "s|image: cockpit:v[0-9.]*|image: cockpit:$TAG|" compose.yaml
echo "== Bauen cockpit:$TAG"
docker build -t "cockpit:$TAG" . > /tmp/cockpit-build.log 2>&1 || { tail -20 /tmp/cockpit-build.log; exit 1; }
echo "== Uebertragen"
docker save "cockpit:$TAG" | gzip -1 | ssh "$HOST" 'gunzip | docker load' | tail -1
scp -q compose.yaml "$HOST:/tmp/cockpit-compose.yaml"
echo "== Starten"
ssh "$HOST" 'cp -a /opt/cockpit/compose.yaml /opt/cockpit/compose.yaml.bak-$(date +%Y%m%d-%H%M) && mv /tmp/cockpit-compose.yaml /opt/cockpit/compose.yaml && cd /opt/cockpit && sudo docker compose up -d 2>&1 | tail -1'
for _ in $(seq 1 30); do
  if curl -fsS -m 3 "$URL/health" 2>/dev/null | grep -q '"ok"'; then break; fi
  sleep 2
done
curl -fsS -m 5 "$URL/health" | head -c 80; echo
echo "== Aufraeumen"
ssh "$HOST" "docker images cockpit --format '{{.Tag}}' | grep -v -x -e '$TAG' -e v0.2 | xargs -r -I{} docker image rm cockpit:{} >/dev/null 2>&1; docker images cockpit --format '{{.Tag}}' | tr '\n' ' '"; echo
docker images cockpit --format '{{.Tag}}' | grep -v -x "$TAG" | xargs -r -I{} docker image rm cockpit:{} >/dev/null 2>&1 || true
if [ -f "$PWFILE" ] && [ -x scripts/cockpit_smoke.sh ]; then
  echo "== Smoketest"
  bash scripts/cockpit_smoke.sh "$URL" "$PWFILE" | tail -3
fi
echo "Fertig: cockpit:$TAG auf $HOST"
