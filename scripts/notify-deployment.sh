#!/usr/bin/env bash
# Cockpit Lifecycle-Hook: meldet einen erfolgreichen App-Start an das Cockpit.
#
# Aufruf aus lifecycle/start.sh:
#
#   /opt/cockpit/scripts/notify-deployment.sh \
#       --app-id "$(cat /etc/auditworkshop/cockpit_app_id)" \
#       --image "ghcr.io/janpow77/auditworkshop-backend:${IMAGE_TAG}" \
#       --git-sha "$GIT_SHA" \
#       --source lifecycle \
#       --status ok \
#       --duration-s "$DURATION"
#
# Erwartet folgende Environment-Variablen (vom Host-ENV bezogen):
#   COCKPIT_URL=https://100.99.159.80:7843    # Cockpit-Basis-URL (Tailscale)
#   LIFECYCLE_HOOK_TOKEN=<token>              # Shared Secret mit Cockpit
#
# Exit 0 bei Erfolg, Exit 1 bei HTTP-Fehler. Lifecycle-Skript sollte einen
# fehlgeschlagenen Hook NICHT als Deployment-Fehler werten — der Hook ist
# best-effort.
set -euo pipefail

usage() {
    cat >&2 <<EOF
Usage: $0 --app-id ID --image IMAGE [--image-digest D] [--git-sha SHA]
          [--source lifecycle|gh-action|manual] [--status ok|failed|started]
          [--actor NAME] [--notes TEXT] [--duration-s SECONDS] [--ts ISO8601]

ENV: COCKPIT_URL, LIFECYCLE_HOOK_TOKEN, COCKPIT_TLS_INSECURE=1 (optional)
EOF
    exit 2
}

APP_ID=""
IMAGE=""
IMAGE_DIGEST=""
GIT_SHA=""
SOURCE="lifecycle"
STATUS="ok"
ACTOR=""
NOTES=""
DURATION_S=""
TS=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        --app-id) APP_ID="$2"; shift 2 ;;
        --image) IMAGE="$2"; shift 2 ;;
        --image-digest) IMAGE_DIGEST="$2"; shift 2 ;;
        --git-sha) GIT_SHA="$2"; shift 2 ;;
        --source) SOURCE="$2"; shift 2 ;;
        --status) STATUS="$2"; shift 2 ;;
        --actor) ACTOR="$2"; shift 2 ;;
        --notes) NOTES="$2"; shift 2 ;;
        --duration-s) DURATION_S="$2"; shift 2 ;;
        --ts) TS="$2"; shift 2 ;;
        -h|--help) usage ;;
        *) echo "Unbekannte Option: $1" >&2; usage ;;
    esac
done

[[ -z "$APP_ID" || -z "$IMAGE" ]] && usage
[[ -z "${COCKPIT_URL:-}" ]] && { echo "COCKPIT_URL nicht gesetzt" >&2; exit 1; }
[[ -z "${LIFECYCLE_HOOK_TOKEN:-}" ]] && { echo "LIFECYCLE_HOOK_TOKEN nicht gesetzt" >&2; exit 1; }

# JSON-Payload sicher bauen (jq erforderlich)
if ! command -v jq >/dev/null 2>&1; then
    echo "jq nicht installiert — bitte: apt install jq" >&2
    exit 1
fi

PAYLOAD=$(jq -n \
    --arg image "$IMAGE" \
    --arg image_digest "$IMAGE_DIGEST" \
    --arg git_sha "$GIT_SHA" \
    --arg source "$SOURCE" \
    --arg status "$STATUS" \
    --arg actor "${ACTOR:-lifecycle-hook}" \
    --arg notes "$NOTES" \
    --arg ts "$TS" \
    --argjson duration "${DURATION_S:-null}" \
    '{
        image: $image,
        image_digest: (if $image_digest == "" then null else $image_digest end),
        git_sha:      (if $git_sha == "" then null else $git_sha end),
        source: $source,
        status: $status,
        actor: $actor,
        notes:        (if $notes == "" then null else $notes end),
        duration_s: $duration
     }
     + (if $ts == "" then {} else {ts: $ts} end)')

CURL_OPTS=(-sS -o /dev/null -w "%{http_code}" --max-time 10
    -X POST
    -H "Content-Type: application/json"
    -H "X-Lifecycle-Token: $LIFECYCLE_HOOK_TOKEN"
    --data "$PAYLOAD")
if [[ "${COCKPIT_TLS_INSECURE:-}" == "1" ]]; then
    CURL_OPTS+=(-k)
fi

HTTP_CODE=$(curl "${CURL_OPTS[@]}" "${COCKPIT_URL%/}/admin/api/apps/${APP_ID}/deployments")
if [[ "$HTTP_CODE" =~ ^2[0-9][0-9]$ ]]; then
    echo "Cockpit-Notify OK ($HTTP_CODE) — app=$APP_ID source=$SOURCE status=$STATUS" >&2
    exit 0
fi
echo "Cockpit-Notify FEHLGESCHLAGEN ($HTTP_CODE) — app=$APP_ID" >&2
exit 1
