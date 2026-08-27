"""Mehrwert-Bausteine der Wand: oeffentliche Dienste, Werkstatt, Kira, Handlungsbedarf.

- Dienste:  jede oeffentliche Adresse wird per HTTPS angefragt (Antwortzeit,
            Status) und das Zertifikat per TLS-Handshake auf Restlaufzeit geprueft.
- Werkstatt: je Host ein Blick in das Projektverzeichnis - Branch, uncommittete
            Aenderungen, letzter Commit und ob eine `.session_resume.md`
            (Pause nach NUC-Aus-Routine) liegt. Antwort auf "Wo war ich?".
- Kira:     juengste Wissens-Eintraege der Memory-API. Der Schluessel bleibt auf
            dem Host, auf dem die API laeuft (aus dessen .env), und verlaesst ihn nie.
- Handlungsbedarf: reine Ableitung aus allen Daten (testbar), leer = alles laeuft.

Alle Sammler sind fehlertolerant: ein kaputter Host oder Dienst kippt nie die Wand.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import shlex
import socket
import ssl
import threading
import time
from datetime import UTC, datetime

import httpx

from ..models import HostRow
from . import wall_config as wc
from .ssh_runner import run_on_host

log = logging.getLogger(__name__)

_lock = threading.Lock()


def _iso(ts: float | int | None) -> str | None:
    if not ts:
        return None
    return datetime.fromtimestamp(ts, UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


# ---------------------------------------------------------------------------
# Oeffentliche Dienste
# ---------------------------------------------------------------------------

_TLS_TTL_S = 600
_tls_cache: dict[str, tuple[float, dict]] = {}


def _tls_info(hostname: str, port: int = 443, timeout: float = 6.0) -> dict:
    """Zertifikat-Ablauf per TLS-Handshake (blockierend, 10 min gecacht)."""
    now = time.time()
    with _lock:
        cached = _tls_cache.get(hostname)
    if cached and now - cached[0] < _TLS_TTL_S:
        return cached[1]
    out: dict = {"tls_bis": None, "tls_tage": None, "tls_aussteller": None, "tls_fehler": None}
    try:
        ctx = ssl.create_default_context()
        with socket.create_connection((hostname, port), timeout=timeout) as sock, ctx.wrap_socket(
            sock, server_hostname=hostname
        ) as tls:
            cert = tls.getpeercert() or {}
        not_after = cert.get("notAfter")
        if not_after:
            exp = datetime.strptime(not_after, "%b %d %H:%M:%S %Y %Z").replace(tzinfo=UTC)
            out["tls_bis"] = exp.isoformat(timespec="seconds").replace("+00:00", "Z")
            out["tls_tage"] = max(0, int((exp - datetime.now(UTC)).total_seconds() // 86400))
        issuer = {}
        for rdn in cert.get("issuer", ()):
            for key, value in rdn:
                issuer[key] = value
        out["tls_aussteller"] = issuer.get("organizationName")
    except (OSError, ssl.SSLError, ValueError) as exc:
        out["tls_fehler"] = str(exc)[:100]
    with _lock:
        _tls_cache[hostname] = (now, out)
    return out


async def _dienst_pruefen(client: httpx.AsyncClient, url: str) -> dict:
    hostname = httpx.URL(url).host
    out: dict = {"url": url, "host": hostname, "ok": False, "status_code": None, "ms": None, "note": None}
    t0 = time.monotonic()
    try:
        resp = await client.get(url, follow_redirects=True)
        if resp.status_code == 404 and not httpx.URL(url).path.strip("/"):
            # API-Hosts ohne Startseite (z. B. MCP) antworten auf /health
            gesund = await client.get(url.rstrip("/") + "/health", follow_redirects=True)
            if gesund.status_code < 400:
                resp = gesund
        out["ms"] = int((time.monotonic() - t0) * 1000)
        out["status_code"] = resp.status_code
        # 4xx heisst: der Dienst antwortet (Anmeldung/Pfad), nur 5xx und Verbindungsfehler sind Ausfaelle
        out["ok"] = resp.status_code < 500
        if resp.status_code >= 400:
            out["note"] = f"HTTP {resp.status_code}"
    except httpx.HTTPError as exc:
        out["ms"] = int((time.monotonic() - t0) * 1000)
        out["note"] = f"{type(exc).__name__}: {str(exc)[:80]}".strip(": ")
    if url.startswith("https://"):
        out.update(await asyncio.to_thread(_tls_info, hostname))
    else:
        out.update({"tls_bis": None, "tls_tage": None, "tls_aussteller": None, "tls_fehler": None})
    return out


async def dienste_pruefen(urls: list[str]) -> list[dict]:
    """Alle oeffentlichen Adressen parallel pruefen (Reihenfolge bleibt erhalten)."""
    uniq = list(dict.fromkeys(u for u in urls if u))
    if not uniq:
        return []
    async with httpx.AsyncClient(
        timeout=httpx.Timeout(8.0, connect=5.0), headers={"User-Agent": "cockpit-wand/1"}
    ) as client:
        res = await asyncio.gather(*(_dienst_pruefen(client, u) for u in uniq), return_exceptions=True)
    out = []
    for u, r in zip(uniq, res, strict=False):
        if isinstance(r, dict):
            out.append(r)
        else:
            log.warning("Dienstpruefung %s: %s", u, r)
            out.append({"url": u, "host": httpx.URL(u).host, "ok": False, "status_code": None, "ms": None,
                        "note": str(r)[:100], "tls_bis": None, "tls_tage": None, "tls_aussteller": None,
                        "tls_fehler": None})
    return out


# ---------------------------------------------------------------------------
# Werkstatt (git-Stand je Projektverzeichnis)
# ---------------------------------------------------------------------------

_WERKSTATT_TTL_S = 180
_ws_cache: dict[str, tuple[float, dict]] = {}
_ws_refreshing: set[str] = set()

_GIT = "git -C \"$r\" -c safe.directory='*'"


def werkstatt_cmd(work_dir: str) -> str:
    """Ein Shell-Durchlauf ueber alle Repos: TSV-Zeile je Repo (rein, testbar)."""
    d = shlex.quote(work_dir.rstrip("/"))
    return (
        f'for g in {d}/*/.git; do r="${{g%/.git}}"; [ -e "$g" ] || continue; '
        'n=$(basename "$r"); '
        f'b=$({_GIT} symbolic-ref --short -q HEAD 2>/dev/null || echo detached); '
        f'dirty=$({_GIT} status --porcelain 2>/dev/null | wc -l); '
        f'ts=$({_GIT} log -1 --format=%ct 2>/dev/null || echo 0); '
        f"msg=$({_GIT} log -1 --format=%s 2>/dev/null | head -c 100 | tr '\\t' ' '); "
        f'ahead=$({_GIT} rev-list --count @{{u}}..HEAD 2>/dev/null || echo -); '
        'pause=0; next=""; if [ -f "$r/.session_resume.md" ]; then pause=$(stat -c %Y "$r/.session_resume.md" 2>/dev/null || echo 0); '
        "next=$(awk 'f&&NF{print substr($0,1,140);exit} /[Nn]ächster Schritt|[Nn]aechster Schritt/{f=1}' \"$r/.session_resume.md\" 2>/dev/null | tr '\\t' ' '); fi; "
        'printf "%s\\t%s\\t%s\\t%s\\t%s\\t%s\\t%s\\t%s\\n" "$n" "$b" "$dirty" "$ts" "$pause" "$ahead" "$msg" "$next"; done'
    )


def parse_werkstatt(stdout: str, hide: list[str], now: float | None = None) -> list[dict]:
    """TSV → Zeilen; Pausen zuerst, dann uncommittete Arbeit, dann nach letztem Commit (rein, testbar)."""
    now = now or time.time()
    rows: list[dict] = []
    for line in stdout.splitlines():
        parts = line.rstrip("\n").split("\t")
        if len(parts) < 6:
            continue
        name, branch, dirty, ts, pause, ahead = parts[:6]
        msg = parts[6] if len(parts) > 6 else ""
        next_step = parts[7].strip() if len(parts) > 7 else ""
        if wc.is_hidden(name, hide):
            continue
        try:
            ts_i = int(ts)
        except ValueError:
            ts_i = 0
        try:
            pause_i = int(pause)
        except ValueError:
            pause_i = 0
        try:
            dirty_i = int(dirty)
        except ValueError:
            dirty_i = 0
        aktiv = max(ts_i, pause_i)
        rows.append({
            "name": name,
            "branch": branch,
            "dirty": dirty_i,
            "ahead": int(ahead) if ahead.isdigit() else None,
            "last_commit": _iso(ts_i),
            "age_h": round((now - ts_i) / 3600, 1) if ts_i else None,
            "message": msg.strip(),
            "pause": _iso(pause_i),
            "pause_age_h": round((now - pause_i) / 3600, 1) if pause_i else None,
            "next_step": re.sub(r"[*_`]+", "", next_step).lstrip("-• ").strip() or None,
            "_aktiv": aktiv,
        })
    # Juengste Aktivitaet zuerst - egal ob Commit oder Pause; Repos ohne Historie ans Ende
    rows.sort(key=lambda r: -r["_aktiv"])
    for r in rows:
        r.pop("_aktiv", None)
    return rows


def _werkstatt_laden(host: HostRow, work_dir: str, hide: list[str]) -> dict:
    try:
        result = run_on_host(host, werkstatt_cmd(work_dir), timeout=90)
    except Exception as exc:  # noqa: BLE001 - Wand darf nie an einem Host scheitern
        return {"host": host.name, "ok": False, "error": str(exc)[:160], "repos": [], "dirty": 0, "pausen": 0,
                "ms": None, "collected_at": _iso(time.time())}
    repos = parse_werkstatt(result.stdout, hide)
    return {
        "host": host.name,
        "ok": bool(repos) or result.ok,
        "error": None if (repos or result.ok) else (result.stderr or f"rc={result.exit_code}")[:160],
        "repos": repos[:40],
        "repo_count": len(repos),
        "dirty": sum(1 for r in repos if r["dirty"]),
        "pausen": sum(1 for r in repos if r["pause"]),
        "ms": result.duration_ms,
        "collected_at": _iso(time.time()),
    }


def werkstatt(host: HostRow, work_dir: str, hide: list[str]) -> dict:
    """Stand des Projektverzeichnisses; beim ersten Aufruf synchron, danach
    stale-while-revalidate (alter Stand sofort, Auffrischung im Hintergrund)."""
    key = f"{host.id}:{work_dir}"
    now = time.time()
    with _lock:
        cached = _ws_cache.get(key)
        frisch = cached is not None and now - cached[0] < _WERKSTATT_TTL_S
        laeuft = key in _ws_refreshing
        if cached is not None and not frisch and not laeuft:
            _ws_refreshing.add(key)
            starten = True
        else:
            starten = False
    if cached is not None:
        if starten:
            def _refresh() -> None:
                try:
                    data = _werkstatt_laden(host, work_dir, hide)
                    with _lock:
                        _ws_cache[key] = (time.time(), data)
                finally:
                    with _lock:
                        _ws_refreshing.discard(key)
            threading.Thread(target=_refresh, name=f"werkstatt-{host.name}", daemon=True).start()
        return cached[1]
    data = _werkstatt_laden(host, work_dir, hide)
    with _lock:
        _ws_cache[key] = (time.time(), data)
    return data


# ---------------------------------------------------------------------------
# Kira (Memory-API) - juengste Wissenseintraege
# ---------------------------------------------------------------------------

_KIRA_TTL_S = 60
_kira_cache: dict[str, tuple[float, dict]] = {}
_WISSEN = {"architecture", "solution", "problem", "reference", "pattern", "workflow", "preference", "feedback"}


def kira_cmd(cfg: dict, limit: int = 40) -> str:
    """curl auf dem API-Host; der Schluessel wird dort aus der .env gelesen (rein, testbar)."""
    base = str(cfg.get("url") or "http://127.0.0.1:8003/api/memory").rstrip("/")
    env_file = str(cfg.get("env_file") or "")
    env_key = str(cfg.get("env_key") or "MEMORY_API_KEY")
    if env_file:
        key = f"$(sed -n 's/^{env_key}=//p' {shlex.quote(env_file)} | head -1 | tr -d '\\r\"')"
    else:
        key = ""
    header = f'-H "X-Memory-API-Key: {key}"' if key else ""
    return (
        f"curl -s -m 8 {header} {shlex.quote(base + '/stats')}; echo; echo '---KIRA---'; "
        f"curl -s -m 8 {header} {shlex.quote(base + '/entries?limit=' + str(limit))}"
    )


def parse_kira(stdout: str, hide: list[str], limit: int = 8) -> dict:
    """Stats + Eintraege aus der Ausgabe; Protokoll-Kategorien und private Projekte bleiben weg (rein, testbar)."""
    out: dict = {"ok": False, "total": None, "entries": [], "note": None}
    teile = stdout.split("---KIRA---", 1)
    try:
        stats = json.loads(teile[0].strip() or "{}")
        if isinstance(stats, dict):
            out["total"] = stats.get("total_entries", stats.get("total"))
            if stats.get("detail") and out["total"] is None:
                out["note"] = str(stats["detail"])[:120]
    except ValueError:
        out["note"] = "Stats nicht lesbar"
    if len(teile) > 1:
        try:
            entries = json.loads(teile[1].strip() or "[]")
        except ValueError:
            entries = []
            out["note"] = out["note"] or "Einträge nicht lesbar"
        if isinstance(entries, list):
            for e in entries:
                if not isinstance(e, dict):
                    continue
                if e.get("category") not in _WISSEN:
                    continue
                project = str(e.get("project") or "")
                text = " ".join(str(e.get("summary") or e.get("content") or "").split())
                text = re.sub(r"^(PROBLEM|LÖSUNG|LOESUNG|REFERENZ|ARCHITEKTUR|SKRIPT|ENTSCHEIDUNG|FEATURE)\s*:\s*", "", text)
                if wc.is_hidden(project, hide) or wc.is_hidden(text[:200], hide):
                    continue
                out["entries"].append({
                    "id": e.get("id"),
                    "category": e.get("category"),
                    "project": project or None,
                    "text": text[:220],
                    "tags": [str(t) for t in (e.get("tags") or [])][:6],
                    "created_at": e.get("created_at"),
                })
                if len(out["entries"]) >= limit:
                    break
            out["ok"] = True
    return out


def kira(host: HostRow, cfg: dict, hide: list[str]) -> dict:
    key = host.id
    now = time.time()
    with _lock:
        cached = _kira_cache.get(key)
    if cached and now - cached[0] < _KIRA_TTL_S:
        return cached[1]
    try:
        result = run_on_host(host, kira_cmd(cfg), timeout=25)
        data = parse_kira(result.stdout, hide)
        if not data["ok"] and not data["note"]:
            data["note"] = (result.stderr or "keine Antwort")[:120]
    except Exception as exc:  # noqa: BLE001
        data = {"ok": False, "total": None, "entries": [], "note": str(exc)[:120]}
    data["host"] = host.name
    with _lock:
        _kira_cache[key] = (now, data)
    return data


# ---------------------------------------------------------------------------
# Handlungsbedarf (rein, testbar)
# ---------------------------------------------------------------------------

_ORDNUNG = {"krit": 0, "warn": 1, "info": 2}


def handlungsbedarf(
    hosts: list[dict],
    projects: list[dict],
    backups: list[dict],
    dienste: list[dict],
    ai_router: dict | None,
    github: dict | None,
    werkstatt_hosts: list[dict],
) -> list[dict]:
    """Leitet aus allen Wand-Daten die Punkte ab, die Aufmerksamkeit brauchen."""
    out: list[dict] = []

    def add(level: str, text: str, *, host: str | None = None, hint: str | None = None, url: str | None = None) -> None:
        out.append({"level": level, "text": text, "host": host, "hint": hint, "url": url})

    for h in hosts:
        st = h.get("stats") or {}
        status = h.get("status")
        if not h.get("is_self") and status not in ("online", "unknown"):
            laptop = bool(re.search(r"macbook|laptop|notebook", f"{h.get('name', '')} {h.get('description', '')}", re.I))
            add("info" if laptop else ("krit" if status in ("offline", "unreachable", "down") else "warn"),
                f"{'Laptop' if laptop else 'Host'} {h['name']} ist {status or 'unbekannt'}", host=h["name"])
            continue
        if st.get("disk_pct") is not None:
            if st["disk_pct"] >= 90:
                add("krit", f"Platte auf {h['name']} zu {int(st['disk_pct'])} % voll", host=h["name"], hint="Aufräumen oder vergrößern")
            elif st["disk_pct"] >= 80:
                add("warn", f"Platte auf {h['name']} zu {int(st['disk_pct'])} % voll", host=h["name"])
        if st.get("mem_pct") is not None and st["mem_pct"] >= 92:
            add("warn", f"RAM auf {h['name']} zu {int(st['mem_pct'])} % belegt", host=h["name"])
        if st.get("load1") is not None and st.get("cpus"):
            if st["load1"] > st["cpus"] * 1.5:
                add("warn", f"Last auf {h['name']} hoch ({str(st['load1']).replace('.', ',')} bei {st['cpus']} CPUs)", host=h["name"])

    # Gestoppte Entwicklungs-Stacks sind Alltag. Es zaehlen Instanzen, die Verkehr bedienen
    # (eigener Tunnel), und auf dem Produktionshost (Self-Host) alles, was registriert ist
    # oder eine oeffentliche Adresse hat. Dev-Hosts bleiben still - ihr Zustand steht im Projektraster.
    prod_hosts = {h.get("name") for h in hosts if h.get("is_self")}
    for p in projects:
        auf_prod = p.get("host") in prod_hosts and (p.get("registered") or p.get("url") or p.get("tunnel"))
        if not (auf_prod or p.get("tunnel")):
            continue
        if p.get("status") == "down":
            add("krit", f"{p.get('title') or p['name']} auf {p['host']}: alle Container aus", host=p["host"], url=p.get("url"))
        elif p.get("status") == "degraded":
            add("warn", f"{p.get('title') or p['name']} auf {p['host']}: {p.get('running')}/{p.get('containers')} Container laufen",
                host=p["host"], url=p.get("url"))

    for b in backups:
        if b.get("status") == "krit":
            add("krit", f"Sicherung {b['name']} ist {int(b.get('age_h') or 0)} h alt", hint="Backup-Lauf prüfen")
        elif b.get("status") == "warn":
            add("warn", f"Sicherung {b['name']} ist {int(b.get('age_h') or 0)} h alt")

    for d in dienste:
        if not d.get("ok"):
            add("krit", f"{d.get('host')} antwortet nicht ({d.get('note') or 'keine Antwort'})", url=d.get("url"))
            continue
        if d.get("tls_tage") is not None:
            if d["tls_tage"] < 7:
                add("krit", f"Zertifikat {d.get('host')} läuft in {d['tls_tage']} Tagen ab", url=d.get("url"))
            elif d["tls_tage"] < 14:
                add("warn", f"Zertifikat {d.get('host')} läuft in {d['tls_tage']} Tagen ab", url=d.get("url"))
        if d.get("ms") is not None and d["ms"] > 3000:
            add("warn", f"{d.get('host')} antwortet langsam ({d['ms']} ms)", url=d.get("url"))

    if ai_router is not None and not ai_router.get("ok"):
        add("warn", "ai-router nicht erreichbar – KI-Konsole ohne Modelle")
    if github and github.get("enabled") and github.get("error"):
        add("warn", f"GitHub: {github['error']}")

    for w in werkstatt_hosts:
        if not w.get("ok") and w.get("error"):
            add("warn", f"Werkstatt {w['host']}: {w['error']}", host=w["host"])
        for r in w.get("repos") or []:
            if r.get("pause") and (r.get("pause_age_h") or 0) <= 24 * 7:
                add("info", f"Pause offen in {r['name']} ({w['host']})", host=w["host"],
                    hint=r.get("next_step") or "Wiederaufnahme aus .session_resume.md")

    out.sort(key=lambda a: _ORDNUNG.get(a["level"], 9))
    return out[:14]
