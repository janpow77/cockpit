"""flow-agent (agent.flowaudit.de) als Datenquelle: Projektinventar aller Hosts, graphify-Stand, Frische.

flow-agent sammelt über seine Host-Agenten (NUC, EVO, MacBook, Hetzner) je Projekt Git-Stand,
Technologien und die graphify-Analyse. Das Cockpit liest nur (Bearer = Lese-Schlüssel aus dem
Vault, Einstellung ``flow_agent``): für die Projektliste der Aufträge und als Kontext für
Vorschlagsläufe. Fehler liefern leere Ergebnisse – die Wand und das Kanban dürfen nie kippen.
"""

from __future__ import annotations

import json
import logging
import threading
import time
import urllib.error
import urllib.request
from datetime import UTC, datetime

log = logging.getLogger(__name__)

CACHE_TTL_S = 300
_cache: dict[str, tuple[float, object]] = {}
_lock = threading.Lock()


def _get(url: str, token: str, pfad: str, timeout: int = 12, ttl: int = CACHE_TTL_S) -> object | None:
    key = f"{url}{pfad}"
    now = time.time()
    with _lock:
        c = _cache.get(key)
    if c and now - c[0] < ttl:
        return c[1]
    req = urllib.request.Request(f"{url.rstrip('/')}{pfad}", headers={"Authorization": f"Bearer {token}", "Accept": "application/json", "User-Agent": "cockpit/1"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            daten = json.loads(r.read().decode("utf-8"))
    except (urllib.error.URLError, urllib.error.HTTPError, ValueError, TimeoutError) as exc:
        log.warning("flow-agent %s: %s", pfad, str(exc)[:120])
        return None
    with _lock:
        _cache[key] = (now, daten)
    return daten


def _host_id(hostname: str, zuordnung: dict[str, str]) -> str:
    """flow-agent-Hostname → Cockpit-Host-Name (Einstellung flow_agent.hosts, sonst Kurzname)."""
    h = (hostname or "").strip()
    if h in zuordnung:
        return zuordnung[h]
    kurz = h.split(".")[0].lower()
    return zuordnung.get(kurz, kurz)


def projekte(url: str, token: str, zuordnung: dict[str, str] | None = None) -> list[dict]:
    """Projektinventar: [{host, hostname, name, pfad, branch, dirty, ahead, behind, technologien, frameworks, status, stand}] (rein bis auf HTTP)."""
    daten = _get(url, token, "/api/v1/projects")
    return projekte_aus(daten, zuordnung or {})


def projekte_aus(daten: object, zuordnung: dict[str, str]) -> list[dict]:
    """Antwort von /api/v1/projects in flache Zeilen (rein, testbar)."""
    out: list[dict] = []
    for agent in daten if isinstance(daten, list) else []:
        if not isinstance(agent, dict):
            continue
        hostname = str(agent.get("hostname") or agent.get("agent_id") or "")
        stand = agent.get("collected_at")
        for p in agent.get("projects") or []:
            if not isinstance(p, dict) or not p.get("path"):
                continue
            out.append({
                "host": _host_id(hostname, zuordnung), "hostname": hostname, "name": str(p.get("name") or str(p["path"]).rstrip("/").rsplit("/", 1)[-1]),
                "pfad": str(p["path"]).rstrip("/"), "branch": p.get("branch"), "dirty": bool(p.get("dirty")),
                "ahead": p.get("ahead"), "behind": p.get("behind"), "technologien": list(p.get("technologies") or []),
                "frameworks": list(p.get("frameworks") or []), "status": str(p.get("status") or "unknown"), "stand": stand,
                "git": bool(p.get("is_git", True)),
            })
    return out


def graphify(url: str, token: str, zuordnung: dict[str, str] | None = None) -> dict[tuple[str, str], dict]:
    """graphify-Stand je (host, projektname): {generiert, knoten, kanten, status}."""
    daten = _get(url, token, "/api/v1/graphify/status")
    return graphify_aus(daten, zuordnung or {})


def graphify_aus(daten: object, zuordnung: dict[str, str]) -> dict[tuple[str, str], dict]:
    out: dict[tuple[str, str], dict] = {}
    for agent in daten if isinstance(daten, list) else []:
        if not isinstance(agent, dict):
            continue
        host = _host_id(str(agent.get("hostname") or ""), zuordnung)
        g = agent.get("graphify") or {}
        generiert = g.get("generated_at")
        for p in g.get("projects") or []:
            if isinstance(p, dict) and p.get("name"):
                out[(host, str(p["name"]))] = {"generiert": generiert, "knoten": int(p.get("node_count") or 0), "kanten": int(p.get("edge_count") or 0), "status": str(p.get("status") or "unknown")}
    return out


def freshness(url: str, token: str) -> dict | None:
    d = _get(url, token, "/api/v1/freshness")
    return d if isinstance(d, dict) else None


def _alter_text(iso: str | None) -> str:
    if not iso:
        return "unbekannt"
    try:
        t = datetime.fromisoformat(str(iso).replace("Z", "+00:00"))
        tage = (datetime.now(UTC) - t).days
        return "heute" if tage <= 0 else f"vor {tage} Tag{'en' if tage != 1 else ''}"
    except ValueError:
        return "unbekannt"


def projekt_kontext(projekt: dict | None, graph: dict | None, findings: list[dict] | None = None) -> str:
    """Kontextblock für den Auftragstext eines Vorschlagslaufs (rein, testbar). Leer, wenn nichts bekannt."""
    if not projekt and not graph:
        return ""
    zeilen = ["", "--- Stand laut flow-agent (agent.flowaudit.de) ---"]
    if projekt:
        git = f"Branch {projekt.get('branch') or '?'}"
        if projekt.get("dirty"):
            git += ", uncommittete Änderungen"
        if projekt.get("ahead"):
            git += f", {projekt['ahead']} Commit(s) vor dem Remote"
        if projekt.get("behind"):
            git += f", {projekt['behind']} Commit(s) hinter dem Remote"
        tech = ", ".join((projekt.get("technologien") or []) + (projekt.get("frameworks") or [])) or "unbekannt"
        zeilen.append(f"Git: {git}. Technologien: {tech}. Zustand: {projekt.get('status')}. Erfasst {_alter_text(projekt.get('stand'))}.")
    if graph:
        zeilen.append(f"graphify: {graph.get('knoten', 0)} Knoten, {graph.get('kanten', 0)} Kanten, Stand {_alter_text(graph.get('generiert'))} ({graph.get('status')}) – Bericht unter graphify-out/<Datum>/GRAPH_REPORT.md.")
    for f in (findings or [])[:5]:
        if isinstance(f, dict) and f.get("message"):
            zeilen.append(f"Hinweis flow-agent: {str(f.get('message'))[:200]}")
    zeilen.append("Berücksichtige diese Punkte in den Vorschlägen (z. B. uncommittete Arbeit sichern, veralteten graphify-Stand erneuern).")
    return "\n".join(zeilen)


# ---------------------------------------------------------------------------
# Zustand für die Wand-Kachel
# ---------------------------------------------------------------------------


def _get_ohne_auth(url: str, pfad: str, timeout: int = 8) -> object | None:
    req = urllib.request.Request(f"{url.rstrip('/')}{pfad}", headers={"Accept": "application/json", "User-Agent": "cockpit/1"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))
    except (urllib.error.URLError, urllib.error.HTTPError, ValueError, TimeoutError) as exc:
        log.warning("flow-agent %s: %s", pfad, str(exc)[:120])
        return None


def zustand(url: str, token: str | None, zuordnung: dict[str, str] | None = None) -> dict:
    """Control Plane, Host-Agenten, Frische-Checks, Meldungen und fehlende Werkzeuge – für die Wand (Fehler → ok=False, nie Ausnahme)."""
    zuordnung = zuordnung or {}
    health = _get_ohne_auth(url, "/api/v1/health")
    if not token:
        return zustand_aus(url, health, None, None, None, None, zuordnung, note="kein Lese-Schlüssel im Vault")
    # Wand-Lauf alle 90 s: kurzer Cache, damit Alter und Zustand der Hosts aktuell bleiben
    return zustand_aus(
        url, health, _get(url, token, "/api/v1/agents", ttl=60), _get(url, token, "/api/v1/freshness", ttl=60),
        _get(url, token, "/api/v1/notifications/summary", ttl=60), _get(url, token, "/api/v1/operations/status", ttl=120), zuordnung,
    )


def zustand_aus(url: str, health: object, agents: object, freshness: object, meldungen: object, operations: object,
                zuordnung: dict[str, str], note: str | None = None) -> dict:
    """Rohantworten → Kachel-Daten (rein, testbar)."""
    ok = isinstance(health, dict) and health.get("status") == "ok"
    out: dict = {
        "ok": ok, "note": note if note else (None if ok else "Control Plane nicht erreichbar"), "url": url,
        "version": (health or {}).get("version") if isinstance(health, dict) else None,
        "hosts": [], "frische": {"status": "unknown", "healthy": 0, "degraded": 0, "unhealthy": 0, "befunde": []},
        "meldungen": {"hosts_offline": [], "hosts_degraded": [], "pending_actions": 0, "failed_actions_recent": 0},
        "stand": datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z"),
    }
    werkzeuge: dict[str, list[str]] = {}
    tmux: dict[str, str | None] = {}
    for a in operations if isinstance(operations, list) else []:
        if not isinstance(a, dict):
            continue
        hn = str(a.get("hostname") or "")
        werkzeuge[hn] = [str(t.get("name")) for t in (a.get("tools") or []) if isinstance(t, dict) and t.get("installed") is False]
        tmux[hn] = (a.get("tmux") or {}).get("status") if isinstance(a.get("tmux"), dict) else None
    for a in agents if isinstance(agents, list) else []:
        if not isinstance(a, dict):
            continue
        hn = str(a.get("hostname") or a.get("agent_id") or "")
        out["hosts"].append({
            "host": _host_id(hn, zuordnung), "hostname": hn, "status": str(a.get("status") or "unknown"),
            "alter_s": a.get("age_seconds"), "projekte": int(a.get("project_count") or 0), "container": int(a.get("container_count") or 0),
            "gpu": int(a.get("gpu_count") or 0), "tmux": tmux.get(hn), "werkzeuge_fehlen": werkzeuge.get(hn, []),
        })
    out["hosts"].sort(key=lambda h: ({"offline": 0, "unhealthy": 0, "degraded": 1, "unknown": 2, "healthy": 3}.get(h["status"], 4), h["host"]))
    if isinstance(freshness, dict):
        f = out["frische"]
        f.update({"status": str(freshness.get("status") or "unknown"), "healthy": int(freshness.get("healthy_count") or 0),
                  "degraded": int(freshness.get("degraded_count") or 0), "unhealthy": int(freshness.get("unhealthy_count") or 0)})
        for b in freshness.get("findings") or []:
            c = b.get("check") if isinstance(b, dict) else None
            if not isinstance(c, dict) or c.get("status") == "healthy":
                continue
            f["befunde"].append({"host": _host_id(str(b.get("hostname") or b.get("agent_id") or ""), zuordnung), "label": str(c.get("label") or c.get("id") or ""),
                                 "status": str(c.get("status") or "unknown"), "detail": str(c.get("detail") or "")[:220]})
        f["befunde"] = sorted(f["befunde"], key=lambda x: {"unhealthy": 0, "degraded": 1, "unknown": 2}.get(x["status"], 3))[:8]
    if isinstance(meldungen, dict):
        m = out["meldungen"]
        m.update({"hosts_offline": [_host_id(str(x), zuordnung) for x in (meldungen.get("hosts_offline") or [])],
                  "hosts_degraded": [_host_id(str(x), zuordnung) for x in (meldungen.get("hosts_degraded") or [])],
                  "pending_actions": int(meldungen.get("pending_actions") or 0), "failed_actions_recent": int(meldungen.get("failed_actions_recent") or 0)})
    return out


def alarme(z: dict) -> list[dict]:
    """Handlungsbedarf aus dem flow-agent-Zustand (rein, testbar): Control Plane weg, Host offline, Check unhealthy, Aktionen fehlgeschlagen."""
    out: list[dict] = []
    url = z.get("url")
    if not z.get("ok"):
        out.append({"level": "warn", "text": f"flow-agent: {z.get('note') or 'nicht erreichbar'}", "host": None, "hint": None, "url": url})
        return out
    for h in z.get("hosts") or []:
        if h.get("status") in ("offline", "unhealthy"):
            out.append({"level": "krit", "text": f"flow-agent: Host {h['host']} {h['status']}", "host": h["host"], "hint": f"zuletzt vor {h.get('alter_s')} s" if h.get("alter_s") is not None else None, "url": url})
    for b in (z.get("frische") or {}).get("befunde") or []:
        if b.get("status") == "unhealthy":
            out.append({"level": "warn", "text": f"flow-agent: {b['label']} auf {b['host']}", "host": b["host"], "hint": b.get("detail"), "url": url})
    m = z.get("meldungen") or {}
    if m.get("failed_actions_recent"):
        out.append({"level": "warn", "text": f"flow-agent: {m['failed_actions_recent']} Aktion(en) fehlgeschlagen", "host": None, "hint": None, "url": url})
    if m.get("pending_actions"):
        out.append({"level": "info", "text": f"flow-agent: {m['pending_actions']} Aktion(en) warten auf Freigabe", "host": None, "hint": None, "url": url})
    return out


# ---------------------------------------------------------------------------
# Host-Kennzahlen aus flow-agent (Ersatz bzw. Rückfall für die eigene SSH-Sonde)
# ---------------------------------------------------------------------------


def _mb(bytes_wert: object) -> int | None:
    try:
        n = int(bytes_wert or 0)
    except (TypeError, ValueError):
        return None
    return round(n / 1048576) if n > 0 else None


def hosts_aus(topologie: object, operations: object, zuordnung: dict[str, str]) -> dict[str, dict]:
    """Kennzahlen je Cockpit-Host aus /topology und /operations/status (rein, testbar).

    Liefert dieselbe Form wie ``host_stats._parse``: load* bleibt leer (flow-agent misst CPU in Prozent),
    dafür kommen Speicher, Laufzeit, Container, GPUs und tmux-Sitzungen ohne eigene SSH-Verbindung.
    """
    aus: dict[str, dict] = {}
    knoten = (topologie or {}).get("nodes") if isinstance(topologie, dict) else None
    if not knoten:
        return aus
    host_je_id: dict[str, str] = {}
    for n in knoten:
        if n.get("kind") != "host":
            continue
        name = _host_id(str(n.get("label") or ""), zuordnung)
        host_je_id[str(n.get("id"))] = name
        m = n.get("metrics") or {}
        md = n.get("metadata") or {}
        aus[name] = {
            "ok": str(n.get("status")) not in ("offline", "unknown"),
            "quelle": "flow-agent", "error": None, "ms": None,
            "load1": None, "load5": None, "load15": None, "cpus": None,
            "cpu_pct": m.get("cpu_percent"),
            "mem_total_mb": _mb(m.get("memory_total_bytes")), "mem_used_mb": _mb(m.get("memory_used_bytes")),
            "mem_pct": (round(100 * m["memory_used_bytes"] / m["memory_total_bytes"], 1)
                        if m.get("memory_total_bytes") else None),
            "disk_total_kb": None, "disk_used_kb": None, "disk_pct": None,
            "uptime_s": int(m.get("uptime_seconds") or 0) or None,
            "temp_c": m.get("cpu_temperature_celsius"),
            "rolle": md.get("role"), "agent_version": md.get("agent_version"), "stand": md.get("last_seen_at"),
            "containers": 0, "gpus": [], "tmux": [],
        }
    for n in knoten:
        name = host_je_id.get(str(n.get("host_id")))
        if name is None or name not in aus:
            continue
        if n.get("kind") == "container" and str(n.get("status")) == "healthy":
            aus[name]["containers"] += 1
        elif n.get("kind") == "gpu":
            m = n.get("metrics") or {}
            aus[name]["gpus"].append({
                "name": n.get("label"), "mem_total_mb": _mb(m.get("memory_total_bytes")),
                "mem_used_mb": _mb(m.get("memory_used_bytes")),
                "util_pct": m.get("utilization_percent"), "temp_c": m.get("temperature_celsius"),
            })
    for a in operations if isinstance(operations, list) else []:
        if not isinstance(a, dict):
            continue
        name = _host_id(str(a.get("hostname") or ""), zuordnung)
        if name not in aus:
            continue
        tm = a.get("tmux") or {}
        aus[name]["tmux"] = [
            {"name": s.get("name"), "attached": bool(s.get("attached")), "created": s.get("created_at"),
             "windows": [{"name": "", "index": str(i + 1), "active": i == 0, "cmd": ""} for i in range(int(s.get("windows") or 0))]}
            for s in (tm.get("sessions") or []) if isinstance(s, dict)
        ]
        aus[name]["werkzeuge_fehlen"] = [str(t.get("name")) for t in (a.get("tools") or []) if isinstance(t, dict) and t.get("installed") is False]
    return aus


def backups_aus(topologie: object, zuordnung: dict[str, str]) -> list[dict]:
    """Sicherungen aus der Topologie (rein, testbar): [{host, ziel, status, letzte, groesse_b}]."""
    out: list[dict] = []
    knoten = (topologie or {}).get("nodes") if isinstance(topologie, dict) else None
    if not knoten:
        return out
    host_je_id = {str(n.get("id")): _host_id(str(n.get("label") or ""), zuordnung) for n in knoten if n.get("kind") == "host"}
    for n in knoten:
        if n.get("kind") != "backup":
            continue
        md = n.get("metadata") or {}
        out.append({
            "host": host_je_id.get(str(n.get("host_id")), "?"), "ziel": n.get("label"),
            "status": n.get("status"), "letzte": md.get("last_success_at"),
            "groesse_b": (n.get("metrics") or {}).get("size_bytes"), "art": md.get("type"),
        })
    return out


def infrastruktur(url: str, token: str | None, zuordnung: dict[str, str] | None = None) -> dict:
    """Hosts, Sicherungen und tmux in einem Zug von der Control Plane (Fehler → leere Ergebnisse)."""
    zuordnung = zuordnung or {}
    if not token:
        return {"hosts": {}, "backups": [], "ok": False}
    topo = _get(url, token, "/api/v1/topology", ttl=60)
    ops = _get(url, token, "/api/v1/operations/status", ttl=60)
    hosts = hosts_aus(topo, ops, zuordnung)
    return {"hosts": hosts, "backups": backups_aus(topo, zuordnung), "ok": bool(hosts)}
