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


def _get(url: str, token: str, pfad: str, timeout: int = 12) -> object | None:
    key = f"{url}{pfad}"
    now = time.time()
    with _lock:
        c = _cache.get(key)
    if c and now - c[0] < CACHE_TTL_S:
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
