"""KI-Nutzung: Auslastung und Limits von Claude (Claude Code), Codex (ChatGPT) und Gemini.

Die Daten liegen auf dem Arbeitsplatz-Host (NUC): Claude Code haelt seine Anmeldung in
~/.claude/.credentials.json - damit liefert api.anthropic.com/api/oauth/usage die
Auslastung des 5-Stunden- und des 7-Tage-Fensters; die Sitzungsprotokolle unter
~/.claude/projects enthalten Tokens je Nachricht. Codex schreibt in jede Sitzung
(~/.codex/sessions) die zuletzt gemeldeten Limits (rate_limits) und Tokenzaehler.
Gemini CLI legt keine Nutzungsdaten ab.

Die Sonde laeuft als Python-Skript AUF dem Host (per SSH oder lokal); Zugangsdaten
verlassen den Host nicht, zurueck kommt nur die Auswertung als JSON. 5 min Cache.
"""

from __future__ import annotations

import json
import logging
import shlex
import threading
import time

from ..models import HostRow
from .ssh_runner import run_on_host

log = logging.getLogger(__name__)

CACHE_TTL_S = 300
_cache: dict[str, tuple[float, dict]] = {}
_lock = threading.Lock()

# Das Skript ist bewusst nur von der Standardbibliothek abhaengig (laeuft mit jedem python3).
SONDE = r'''
import json, os, glob, collections, urllib.request
from datetime import datetime, timedelta, timezone
CFG = json.loads(os.environ.get("KI_CFG") or "{}")
jetzt = datetime.now(timezone.utc)
seit = jetzt - timedelta(days=7)
tage = [(jetzt - timedelta(days=i)).strftime("%Y-%m-%d") for i in range(6, -1, -1)]
out = {"claude": {"verfuegbar": False}, "codex": {"verfuegbar": False}, "gemini": {"verfuegbar": False, "hinweis": "Gemini CLI legt keine Nutzungsdaten ab"}}

# ---- Claude: Limits ueber die Anmeldung von Claude Code, Tokens aus den Protokollen
cred = os.path.expanduser(CFG.get("claude_credentials") or "~/.claude/.credentials.json")
try:
    o = json.load(open(cred)).get("claudeAiOauth") or {}
    tok = o.get("accessToken")
    c = {"verfuegbar": True, "plan": o.get("subscriptionType"), "stufe": o.get("rateLimitTier"), "limits": {}, "hinweis": None}
    if tok:
        req = urllib.request.Request("https://api.anthropic.com/api/oauth/usage", headers={"Authorization": "Bearer " + tok, "anthropic-beta": "oauth-2025-04-20", "User-Agent": "cockpit-wand/1"})
        try:
            with urllib.request.urlopen(req, timeout=12) as r:
                u = json.loads(r.read().decode())
            for k, label in (("five_hour", "5 Stunden"), ("seven_day", "7 Tage"), ("seven_day_opus", "7 Tage Opus"), ("seven_day_sonnet", "7 Tage Sonnet")):
                v = u.get(k)
                if isinstance(v, dict) and v.get("utilization") is not None:
                    c["limits"][k] = {"label": label, "prozent": float(v["utilization"]), "reset": v.get("resets_at")}
            extra = u.get("extra_usage") or {}
            c["extra_usage"] = bool(extra.get("is_enabled")) if isinstance(extra, dict) else None
        except Exception as e:
            c["hinweis"] = "Auslastung nicht abrufbar: " + str(e)[:80]
    else:
        c["hinweis"] = "kein Zugangstoken in der Claude-Code-Anmeldung"
    # Tokens je Tag und Modell aus den Sitzungsprotokollen (Duplikate ueber requestId)
    tag = collections.defaultdict(lambda: collections.defaultdict(lambda: [0, 0, 0, 0]))
    seen = set()
    for f in glob.glob(os.path.expanduser(CFG.get("claude_projekte") or "~/.claude/projects") + "/*/*.jsonl"):
        try:
            if datetime.fromtimestamp(os.path.getmtime(f), timezone.utc) < seit: continue
        except OSError: continue
        try:
            with open(f, encoding="utf-8", errors="ignore") as fh:
                for line in fh:
                    if '"usage"' not in line: continue
                    try: d = json.loads(line)
                    except ValueError: continue
                    m = d.get("message") or {}
                    u = m.get("usage") if isinstance(m, dict) else None
                    if not u: continue
                    ts = str(d.get("timestamp", ""))[:10]
                    if ts not in tage: continue
                    key = d.get("requestId") or d.get("uuid")
                    if key in seen: continue
                    seen.add(key)
                    t = tag[ts][str(m.get("model") or "?")]
                    t[0] += int(u.get("input_tokens") or 0); t[1] += int(u.get("output_tokens") or 0)
                    t[2] += int(u.get("cache_read_input_tokens") or 0); t[3] += int(u.get("cache_creation_input_tokens") or 0)
        except OSError: continue
    c["tage"] = [{"tag": d, "out": sum(v[1] for v in tag[d].values()), "kontext": sum(v[0] + v[2] + v[3] for v in tag[d].values())} for d in tage]
    heute = tag[tage[-1]]
    c["heute"] = {"out": sum(v[1] for v in heute.values()), "kontext": sum(v[0] + v[2] + v[3] for v in heute.values()), "modelle": {m: {"out": v[1], "kontext": v[0] + v[2] + v[3]} for m, v in heute.items()}}
    out["claude"] = c
except Exception as e:
    out["claude"] = {"verfuegbar": False, "hinweis": str(e)[:100]}

# ---- Codex: Limits und Tokens aus den Sitzungsprotokollen
try:
    basis = os.path.expanduser(CFG.get("codex_sessions") or "~/.codex/sessions")
    dateien = []
    for root, _dirs, files in os.walk(basis):
        for n in files:
            if n.endswith(".jsonl"):
                p = os.path.join(root, n)
                try:
                    if datetime.fromtimestamp(os.path.getmtime(p), timezone.utc) >= seit: dateien.append(p)
                except OSError: pass
    letzte_limits, letzte_ts = None, ""
    je_tag = collections.defaultdict(lambda: [0, 0, 0])  # out, kontext, sitzungen
    for p in dateien:
        maxi = None; tag_s = None; limits = None; ts_l = ""
        try:
            with open(p, encoding="utf-8", errors="ignore") as fh:
                for line in fh:
                    if '"token_count"' not in line: continue
                    try: d = json.loads(line)
                    except ValueError: continue
                    pl = d.get("payload") or d
                    if pl.get("type") != "token_count": continue
                    ts = str(d.get("timestamp") or "")
                    tag_s = tag_s or ts[:10]
                    info = pl.get("info") or {}
                    tot = info.get("total_token_usage") or {}
                    if tot: maxi = tot
                    rl = pl.get("rate_limits")
                    if rl: limits, ts_l = rl, ts
        except OSError: continue
        if maxi and tag_s in tage:
            je_tag[tag_s][0] += int(maxi.get("output_tokens") or 0)
            je_tag[tag_s][1] += int(maxi.get("input_tokens") or 0) + int(maxi.get("cached_input_tokens") or 0)
            je_tag[tag_s][2] += 1
        if limits and ts_l >= letzte_ts:
            letzte_limits, letzte_ts = limits, ts_l
    cx = {"verfuegbar": bool(dateien), "limits": {}, "plan": None, "stand": letzte_ts or None}
    if letzte_limits:
        cx["plan"] = letzte_limits.get("plan_type")
        for k, label in (("primary", None), ("secondary", None)):
            v = letzte_limits.get(k)
            if isinstance(v, dict) and v.get("used_percent") is not None:
                minuten = int(v.get("window_minutes") or 0)
                lab = "7 Tage" if minuten >= 10000 else ("5 Stunden" if minuten <= 300 else f"{minuten // 60} Stunden")
                rs = v.get("resets_at")
                cx["limits"][k] = {"label": lab, "prozent": float(v["used_percent"]), "reset": datetime.fromtimestamp(rs, timezone.utc).isoformat() if isinstance(rs, (int, float)) else rs}
    cx["tage"] = [{"tag": d, "out": je_tag[d][0], "kontext": je_tag[d][1], "sitzungen": je_tag[d][2]} for d in tage]
    cx["heute"] = {"out": je_tag[tage[-1]][0], "kontext": je_tag[tage[-1]][1], "sitzungen": je_tag[tage[-1]][2]}
    out["codex"] = cx
except Exception as e:
    out["codex"] = {"verfuegbar": False, "hinweis": str(e)[:100]}

print(json.dumps(out, ensure_ascii=False))
'''


def _befehl(cfg: dict) -> str:
    env = json.dumps({k: cfg[k] for k in ("claude_credentials", "claude_projekte", "codex_sessions") if cfg.get(k)})
    return f"KI_CFG={shlex.quote(env)} python3 - <<'COCKPIT_KI'\n{SONDE}\nCOCKPIT_KI"


def abfragen(host: HostRow, cfg: dict, *, refresh: bool = False) -> dict:
    """KI-Nutzung vom Arbeitsplatz-Host; Fehler liefern {ok: False, hinweis}."""
    now = time.time()
    with _lock:
        cached = _cache.get(host.id)
    if cached and not refresh and now - cached[0] < CACHE_TTL_S:
        return cached[1]
    try:
        result = run_on_host(host, _befehl(cfg), timeout=60)
        daten = json.loads(result.stdout or "{}")
        daten["ok"] = bool(daten)
        if not daten.get("ok"):
            daten["hinweis"] = (result.stderr or "keine Ausgabe")[:160]
    except Exception as exc:  # noqa: BLE001 - Kachel darf die Wand nie kippen
        daten = {"ok": False, "hinweis": str(exc)[:160], "claude": {"verfuegbar": False}, "codex": {"verfuegbar": False}, "gemini": {"verfuegbar": False}}
    daten["host"] = host.name
    with _lock:
        _cache[host.id] = (now, daten)
    return daten


def alarme(daten: dict, warn_pct: float = 85.0) -> list[dict]:
    """Alarme, wenn ein Limit fast erreicht ist (rein, testbar)."""
    out: list[dict] = []
    for dienst, name in (("claude", "Claude"), ("codex", "Codex/ChatGPT")):
        d = daten.get(dienst) or {}
        for lim in (d.get("limits") or {}).values():
            p = lim.get("prozent")
            if p is None:
                continue
            if p >= warn_pct:
                reset = str(lim.get("reset") or "")[:16].replace("T", " ")
                out.append({
                    "level": "krit" if p >= 97 else "warn",
                    "text": f"{name}: Limit {lim.get('label')} zu {int(p)} % ausgeschöpft",
                    "host": None, "hint": f"Reset {reset} UTC" if reset else None, "url": None,
                })
    return out
