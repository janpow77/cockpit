#!/usr/bin/env bash

set -u

if [[ $# -ne 2 ]]; then
    echo "FEHLER Aufruf: $0 <base-url> <passwort-datei>"
    exit 2
fi

BASE_URL=${1%/}
PASSWORD_FILE=$2
FAILURES=0
TMP_DIR=$(mktemp -d)
trap 'rm -rf -- "$TMP_DIR"' EXIT

ok() {
    printf 'OK %s\n' "$*"
}

warn() {
    printf 'WARNUNG %s\n' "$*"
}

fail() {
    printf 'FEHLER %s\n' "$*"
    FAILURES=$((FAILURES + 1))
}

is_json() {
    jq -e . "$1" >/dev/null 2>&1
}

request() {
    local method=$1
    local path=$2
    local output=$3
    local max_time=$4
    local data_file=${5:-}
    local -a args=(
        --silent --show-error
        --output "$output"
        --write-out '%{http_code}'
        --max-time "$max_time"
        --request "$method"
        --header "Authorization: Bearer $TOKEN"
    )
    if [[ -n $data_file ]]; then
        args+=(--header 'Content-Type: application/json' --data-binary "@$data_file")
    fi
    curl "${args[@]}" "$BASE_URL$path"
}

if [[ ! -r $PASSWORD_FILE ]]; then
    fail "Passwortdatei ist nicht lesbar"
    exit "$FAILURES"
fi
if ! command -v curl >/dev/null 2>&1 || ! command -v jq >/dev/null 2>&1; then
    fail "curl und jq werden benötigt"
    exit "$FAILURES"
fi

LOGIN_BODY="$TMP_DIR/login-request.json"
jq -Rs '{username:"admin", password:(sub("[\\r\\n]+$"; ""))}' <"$PASSWORD_FILE" >"$LOGIN_BODY"
LOGIN_RESPONSE="$TMP_DIR/login-response.json"
LOGIN_CODE=$(curl --silent --show-error --output "$LOGIN_RESPONSE" --write-out '%{http_code}' \
    --max-time 20 --header 'Content-Type: application/json' --data-binary "@$LOGIN_BODY" \
    "$BASE_URL/admin/api/auth/login")
if [[ $LOGIN_CODE != 200 ]] || ! is_json "$LOGIN_RESPONSE"; then
    fail "Login (HTTP $LOGIN_CODE)"
    exit "$FAILURES"
fi
TOKEN=$(jq -r '.token // empty' "$LOGIN_RESPONSE")
if [[ -z $TOKEN ]]; then
    fail "Login-Antwort enthält kein token-Feld"
    exit "$FAILURES"
fi
ok "Login"

HEALTH="$TMP_DIR/health.json"
HEALTH_CODE=$(curl --silent --show-error --output "$HEALTH" --write-out '%{http_code}' \
    --max-time 20 "$BASE_URL/health")
if [[ $HEALTH_CODE == 200 ]] && is_json "$HEALTH" && jq -e '.status == "ok"' "$HEALTH" >/dev/null; then
    VERSION=$(jq -r '.version // "unbekannt"' "$HEALTH")
    ok "health: status=ok, Version=$VERSION"
else
    fail "health (HTTP $HEALTH_CODE oder status nicht ok)"
fi

OVERVIEW="$TMP_DIR/overview.json"
OVERVIEW_CODE=$(request GET /admin/api/overview "$OVERVIEW" 170)
if [[ $OVERVIEW_CODE != 200 ]] || ! is_json "$OVERVIEW"; then
    fail "overview (HTTP $OVERVIEW_CODE oder ungültiges JSON)"
else
    if jq -e 'has("hosts") and has("projects") and has("alerts") and has("dienste") and has("werkstatt") and has("kira") and has("ai_router") and has("github") and has("hero")' "$OVERVIEW" >/dev/null; then
        ok "overview: Pflichtfelder vorhanden"
    else
        fail "overview: mindestens ein Pflichtfeld fehlt"
    fi
    ONLINE_COUNT=$(jq '[.hosts[]? | select(.status == "online")] | length' "$OVERVIEW")
    if ((ONLINE_COUNT >= 1)); then
        ok "overview: $ONLINE_COUNT Host(s) online"
    else
        fail "overview: kein Host online"
    fi
    if jq -e '.hero.kpis | type == "array"' "$OVERVIEW" >/dev/null; then
        ok "overview: hero.kpis ist eine Liste"
    else
        fail "overview: hero.kpis ist keine Liste"
    fi
    DEMO_READY=$(jq -r '.hero.demo_ready // false' "$OVERVIEW")
    ok "overview: hero.demo_ready=$DEMO_READY"

    IFS=',' read -r -a TOLERATED_HOSTS <<<"${COCKPIT_SMOKE_TOLERATED_HOSTS:-}"
    SERVICE_COUNT=$(jq '.dienste | length' "$OVERVIEW")
    SERVICE_FAILURES=0
    while IFS=$'\t' read -r service_host service_note; do
        [[ -n $service_host ]] || continue
        tolerated=false
        for tolerated_host in "${TOLERATED_HOSTS[@]}"; do
            if [[ -n $tolerated_host && $service_host == "$tolerated_host" ]]; then
                tolerated=true
                break
            fi
        done
        if $tolerated; then
            warn "overview: tolerierter Dienst $service_host ist nicht ok (${service_note:-keine Angabe})"
        else
            fail "overview: Dienst $service_host ist nicht ok (${service_note:-keine Angabe})"
            SERVICE_FAILURES=$((SERVICE_FAILURES + 1))
        fi
    done < <(jq -r '.dienste[]? | select(.ok != true) | [(.host // .url // "unbekannt"), (.note // "keine Angabe")] | @tsv' "$OVERVIEW")
    if ((SERVICE_FAILURES == 0)); then
        ok "overview: Dienste geprüft ($SERVICE_COUNT insgesamt, keine nicht tolerierten Ausfälle)"
    fi

    CRIT_COUNT=$(jq '[.alerts[]? | select(.level == "krit")] | length' "$OVERVIEW")
    if ((CRIT_COUNT > 0)); then
        warn "overview: $CRIT_COUNT kritische(r) Alert(s)"
    else
        ok "overview: keine kritischen Alerts"
    fi
fi

MODELS="$TMP_DIR/models.json"
MODELS_CODE=$(request GET /admin/api/chat/models "$MODELS" 30)
MODEL=""
if [[ $MODELS_CODE == 200 ]] && is_json "$MODELS" && jq -e '.router_ok == true and (.models | type == "array" and length >= 1)' "$MODELS" >/dev/null; then
    MODEL=$(jq -r '.models[0].tag // empty' "$MODELS")
    if [[ -n $MODEL ]]; then
        ok "chat/models: Router ok, $(jq '.models | length' "$MODELS") Modell(e) freigegeben"
    else
        fail "chat/models: erstes Modell hat kein tag-Feld"
    fi
else
    fail "chat/models (HTTP $MODELS_CODE, Router nicht ok oder kein Modell)"
fi

MCP="$TMP_DIR/mcp.json"
MCP_CODE=$(request GET /admin/api/mcp/servers "$MCP" 60)
if [[ $MCP_CODE != 200 ]] || ! is_json "$MCP"; then
    warn "mcp/servers: HTTP $MCP_CODE oder ungültiges JSON"
elif jq -e '.servers[]? | select(.id == "flowaudit") | .inspect.ok == true and (.inspect.tools | type == "array" and length >= 1)' "$MCP" >/dev/null; then
    MCP_TOOLS=$(jq '[.servers[]? | select(.id == "flowaudit") | .inspect.tools[]?] | length' "$MCP")
    ok "mcp/servers: flowaudit inspect ok, $MCP_TOOLS Werkzeug(e)"
else
    warn "mcp/servers: flowaudit fehlt, inspect nicht ok oder kein Werkzeug vorhanden"
fi

if [[ -n $MODEL ]]; then
    CHAT_BODY="$TMP_DIR/chat-request.json"
    jq -n --arg model "$MODEL" '{model:$model, messages:[{role:"user",content:"Antworte nur mit dem Wort Bereit."}], rag:"off", temperature:0.1}' >"$CHAT_BODY"
    CHAT_STREAM="$TMP_DIR/chat.sse"
    CHAT_CODE=$(curl --silent --show-error --no-buffer --output "$CHAT_STREAM" --write-out '%{http_code}' \
        --max-time 120 --request POST --header "Authorization: Bearer $TOKEN" \
        --header 'Content-Type: application/json' --data-binary "@$CHAT_BODY" "$BASE_URL/admin/api/chat")
    DELTA_COUNT=$(sed -n 's/^data: //p' "$CHAT_STREAM" | jq -s '[.[] | select(.delta? != null)] | length' 2>/dev/null || printf '0')
    DONE_COUNT=$(sed -n 's/^data: //p' "$CHAT_STREAM" | jq -s '[.[] | select(.done? == true)] | length' 2>/dev/null || printf '0')
    if [[ $CHAT_CODE == 200 ]] && ((DELTA_COUNT >= 1)) && ((DONE_COUNT >= 1)); then
        ANSWER=$(sed -n 's/^data: //p' "$CHAT_STREAM" | jq -sr '[.[] | .delta? // empty] | join("")' | tr '\r\n\t' '   ' | cut -c1-80)
        ok "chat SSE: delta und done empfangen; Antwort=${ANSWER:-<leer>}"
    else
        fail "chat SSE (HTTP $CHAT_CODE, delta=$DELTA_COUNT, done=$DONE_COUNT)"
    fi
else
    fail "chat SSE kann ohne freigegebenes Modell nicht geprüft werden"
fi

DEMO_BODY="$TMP_DIR/demo-request.json"
printf '%s\n' '{"neu":false}' >"$DEMO_BODY"
DEMO_RESPONSE="$TMP_DIR/demo-response.json"
DEMO_CODE=$(request POST /admin/api/overview/demo "$DEMO_RESPONSE" 660 "$DEMO_BODY")
if [[ $DEMO_CODE == 200 ]] && is_json "$DEMO_RESPONSE" && jq -e '.ok == true' "$DEMO_RESPONSE" >/dev/null; then
    SKIPPED=$(jq -r '.uebersprungen // false' "$DEMO_RESPONSE")
    ok "overview/demo neu=false: ok=true, uebersprungen=$SKIPPED"
else
    fail "overview/demo neu=false (HTTP $DEMO_CODE oder ok nicht true)"
fi

CONFIG="$TMP_DIR/config.json"
CONFIG_CODE=$(request GET /admin/api/overview/config "$CONFIG" 30)
if [[ $CONFIG_CODE == 200 ]] && is_json "$CONFIG" && \
    jq -e 'has("hide") and has("links") and has("hero") and has("chat_models") and has("mcp_servers") and has("work_dirs") and has("kira") and has("prod_hosts")' "$CONFIG" >/dev/null; then
    ok "overview/config: Pflichtfelder vorhanden"
else
    fail "overview/config (HTTP $CONFIG_CODE oder Pflichtfeld fehlt)"
fi

if ((FAILURES > 0)); then
    printf 'FEHLER Smoketest beendet: %s Fehler\n' "$FAILURES"
    exit "$FAILURES"
fi
ok "Smoketest vollständig erfolgreich"
