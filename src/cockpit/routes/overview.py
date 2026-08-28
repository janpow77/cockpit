"""Wand-Aggregat: Hosts, Compose-Projekte, Sonden, GitHub, Sicherungen, Ereignisse.

Nur lesend (Leitprinzip M18: Single Pane of Glass, verlinkt zum Handeln).
Ausnahme: POST /demo startet die HPP-Demo ueber deren regulaere API mit
Zugangsdaten aus dem Vault - das ist die eine Handlung, die die Wand kennt.
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import shlex
import time
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..auth import require_auth
from ..crud import apps as crud_apps
from ..crud import audit as crud_audit
from ..crud import deployments as crud_deployments
from ..crud import hosts as crud_hosts
from ..crud import secrets as crud_secrets
from ..crud import traffic as crud_traffic
from ..db import get_session
from ..models import HostRow
from ..services import ai_router_client, docker_inspect, github_client, host_stats
from ..services import flow_agent as fa
from ..services import ki_nutzung as kn
from ..services import wall_config as wc
from ..services import wall_extras as wx
from ..services.secret_vault import VaultDecryptError, VaultDisabledError, decrypt

log = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/api/overview", tags=["overview"])


# ---------------------------------------------------------------------------
# Helfer (rein, testbar)
# ---------------------------------------------------------------------------


def _iso_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _secret_value(session: Session, key: str | None) -> str | None:
    """Klartext eines Vault-Secrets fuer serverseitige Aufrufe (kein Reveal an den Client)."""
    if not key:
        return None
    row = crud_secrets.get_by_key(session, key)
    if row is None:
        return None
    try:
        return decrypt(row.value_encrypted)
    except (VaultDisabledError, VaultDecryptError) as exc:
        log.warning("Secret %s nicht lesbar: %s", key, exc)
        return None


_PORT_RE = re.compile(r"(?P<ip>[\d.]+|\[[0-9a-f:]+\]|::):(?P<port>\d+)->(?P<cport>\d+)/tcp")


def intern_urls(containers: list[dict], host_ip: str | None, limit: int = 3) -> list[dict]:
    """Interne Adressen eines Projekts aus veroeffentlichten Ports (rein, testbar).

    Ports, die auf 0.0.0.0/:: oder die Tailscale-IP gebunden sind, sind ueber das
    Mesh erreichbar: http://<tailscale-ip>:<port>. Reine 127.0.0.1-Bindungen bleiben weg."""
    if not host_ip:
        return []
    out: list[dict] = []
    gesehen: set[int] = set()
    for c in containers:
        for m in _PORT_RE.finditer(c.get("ports") or ""):
            ip, port = m.group("ip"), int(m.group("port"))
            if ip.startswith("127.") or ip == "[::1]":
                continue
            if ip not in ("0.0.0.0", "::", "[::]") and ip != host_ip:
                continue
            if port in gesehen:
                continue
            gesehen.add(port)
            out.append({"url": f"http://{host_ip}:{port}", "service": c.get("service") or c.get("name", ""), "port": port})
    out.sort(key=lambda e: e["port"])
    return out[:limit]


def build_projects(
    host: HostRow,
    projects: list[dict],
    apps: list[Any],
    cfg: wc.WallConfig,
    deploy_for_app: dict[str, dict],
) -> list[dict]:
    """Verbindet entdeckte Compose-Projekte mit Registrierung, Link und Label."""
    out: list[dict] = []
    host_apps = [a for a in apps if a.host_id == host.id and a.enabled]
    for p in projects:
        names = p.get("names") or []
        if wc.is_hidden(p["name"], cfg.hide) or any(wc.is_hidden(n, cfg.hide) for n in names):
            continue
        registered = None
        for a in host_apps:
            prefix = (a.container_filter or "").removeprefix("name=").strip()
            if (prefix and any(n.startswith(prefix) for n in names)) or a.name == p["name"]:
                registered = a
                break
        lab = wc.label_for(p["name"], names, cfg.labels)
        out.append({
            "host": host.name,
            "name": p["name"],
            "title": lab.get("title") or p["name"],
            "sub": lab.get("sub") or "",
            "containers": p["containers"],
            "running": p["running"],
            "status": p["status"],
            "images": p.get("images", []),
            "names": names[:8],
            "url": wc.link_for(p["name"], names, cfg.links),
            "intern": intern_urls(p.get("container_rows") or [], getattr(host, "tailscale_ip", None)),
            "tunnel": any(
                "cloudflared" in (c.get("name") or "") and (c.get("state") in (None, "running"))
                for c in (p.get("container_rows") or [{"name": n} for n in names])
            ),
            "registered": bool(registered),
            "app_id": registered.id if registered else None,
            "app_status": registered.last_status if registered else None,
            "last_check_at": registered.last_check_at if registered else None,
            "deploy": deploy_for_app.get(registered.id) if registered else None,
        })
    return out


def waehle_hero(projects: list[dict], hero: dict) -> dict | None:
    """Hero-Projekt: Name/Titel passend, bevorzugt auf dem konfigurierten Host,
    sonst die Instanz mit Tunnel (Prod), sonst die erste (rein, testbar)."""
    wanted = str(hero.get("project") or "").lower()
    if not wanted:
        return None
    kandidaten = [
        p for p in projects
        if p["name"].lower() == wanted or wanted in p["name"].lower() or wanted in (p.get("title") or "").lower()
    ]
    if not kandidaten:
        return None
    host = str(hero.get("host") or "")
    for p in kandidaten:
        if host and p["host"] == host:
            return p
    for p in kandidaten:
        if p.get("tunnel"):
            return p
    return kandidaten[0]


def _newest_backups(backup_dir: str) -> list[dict]:
    """Juengste Sicherungsdatei je Praefix (Teil vor dem ersten '-')."""
    if not backup_dir or not os.path.isdir(backup_dir):
        return []
    best: dict[str, dict] = {}
    now = time.time()
    try:
        with os.scandir(backup_dir) as it:
            for entry in it:
                if not entry.is_file() or entry.name.endswith((".log", ".txt", ".md")):
                    continue
                st = entry.stat()
                prefix = entry.name.split("-", 1)[0] or entry.name
                cand = {
                    "name": prefix,
                    "file": entry.name,
                    "mtime": datetime.fromtimestamp(st.st_mtime, UTC).isoformat(timespec="seconds").replace("+00:00", "Z"),
                    "size_bytes": st.st_size,
                    "age_h": round((now - st.st_mtime) / 3600, 1),
                }
                if prefix not in best or st.st_mtime > best[prefix]["_mtime"]:
                    cand["_mtime"] = st.st_mtime
                    best[prefix] = cand
    except OSError as exc:
        log.warning("Sicherungsverzeichnis %s nicht lesbar: %s", backup_dir, exc)
        return []
    rows = sorted(best.values(), key=lambda b: b["name"])
    for r in rows:
        r.pop("_mtime", None)
        r["status"] = "ok" if r["age_h"] <= 30 else ("warn" if r["age_h"] <= 72 else "krit")
    return rows


_probe_tokens: dict[str, tuple[float, str]] = {}
_PROBE_TOKEN_TTL_S = 30 * 60


async def _probe_login(session: Session, probe: dict) -> tuple[str | None, str | None]:
    """Anmeldung fuer Sonden mit login_url (OAuth2-Passwortformular wie bei HPP);
    Token 30 min gemerkt. Liefert (token, fehlertext)."""
    pid = str(probe.get("id") or probe.get("url"))
    hit = _probe_tokens.get(pid)
    if hit and time.time() - hit[0] < _PROBE_TOKEN_TTL_S:
        return hit[1], None
    user = _secret_value(session, probe.get("user_secret"))
    password = _secret_value(session, probe.get("password_secret"))
    if not user or not password:
        return None, f"Secrets „{probe.get('user_secret')}“/„{probe.get('password_secret')}“ fehlen im Vault"
    try:
        async with httpx.AsyncClient(timeout=10.0) as c:
            resp = await c.post(probe["login_url"], data={"username": user, "password": password})
    except httpx.HTTPError as exc:
        return None, f"Anmeldung: {str(exc)[:80]}"
    if resp.status_code >= 400:
        return None, f"Anmeldung fehlgeschlagen (HTTP {resp.status_code})"
    token = (resp.json() or {}).get("access_token") if resp.headers.get("content-type", "").startswith("application/json") else None
    if not token:
        return None, "Anmeldung ohne access_token"
    _probe_tokens[pid] = (time.time(), token)
    return token, None


async def _run_probe(session: Session, probe: dict) -> dict:
    """Eine Sonde: JSON holen, konfigurierte Felder als Kennzahlen liefern.
    Zugang entweder ueber ein festes Secret (secret_key) oder eine Anmeldung (login_url)."""
    out = {"id": probe.get("id"), "label": probe.get("label"), "ok": False, "kpis": [], "note": None}
    url = probe.get("url")
    if not url:
        out["note"] = "keine URL"
        return out
    headers = {}
    secret_key = probe.get("secret_key")
    if probe.get("login_url"):
        token, fehler = await _probe_login(session, probe)
        if not token:
            out["note"] = fehler
            return out
        headers["Authorization"] = f"Bearer {token}"
    elif secret_key:
        value = _secret_value(session, secret_key)
        if not value:
            out["note"] = f"Secret „{secret_key}“ fehlt im Vault"
            return out
        headers[probe.get("header") or "Authorization"] = f"{probe.get('header_prefix', '')}{value}"
    try:
        async with httpx.AsyncClient(timeout=8.0) as c:
            resp = await c.get(url, headers=headers)
            if resp.status_code == 401 and probe.get("login_url"):
                _probe_tokens.pop(str(probe.get("id") or probe.get("url")), None)
                token, fehler = await _probe_login(session, probe)
                if token:
                    resp = await c.get(url, headers={"Authorization": f"Bearer {token}"})
        if resp.status_code >= 400:
            out["note"] = f"HTTP {resp.status_code}"
            return out
        data = resp.json()
    except (httpx.HTTPError, ValueError) as exc:
        out["note"] = str(exc)[:120]
        return out
    seen: set[str] = set()
    for f in probe.get("fields") or []:
        key, label = f.get("key"), f.get("label") or f.get("key")
        if key in data and label not in seen:
            seen.add(label)
            out["kpis"].append({"label": label, "value": data[key]})
    out["ok"] = True
    return out


def _events(session: Session, github_commits: list[dict]) -> list[dict]:
    events: list[dict] = []
    for a in crud_audit.list_audit(session, limit=15):
        events.append({"ts": a.ts, "kind": "audit", "text": f"{a.action} {a.target or ''}".strip()})
    for d in crud_deployments.list_recent(session, limit=10):
        events.append({"ts": d.ts, "kind": "deploy", "text": f"Deploy {d.image} {(d.git_sha or '')[:7]} · {d.status}"})
    for c in github_commits[:15]:
        if c.get("date"):
            events.append({"ts": c["date"], "kind": "commit", "text": f"{c['repo'].split('/')[-1]} {c['sha']} · {c['message']}"})
    events.sort(key=lambda e: e.get("ts") or "", reverse=True)
    return events[:30]


def _zugriffe_24h(session: Session, server_name: str) -> dict:
    """Zugriffe der letzten 24 h je Dienst aus den Caddy-Samples (Stundenverlauf)."""
    to_ts = datetime.now(UTC).replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
    from_ts = to_ts - timedelta(hours=24)
    try:
        punkte = crud_traffic.series(
            session, app_id=None, host_id=None, server_name=server_name,
            bucket_size="1h", from_ts=from_ts, to_ts=to_ts,
        )
    except Exception as exc:  # noqa: BLE001 - Verkehr ist Beiwerk
        log.debug("Traffic %s: %s", server_name, exc)
        return {"requests_24h": None, "verlauf": [], "fehler_5xx": None}
    je_stunde = {pt["bucket_ts"]: pt for pt in punkte}
    verlauf = []
    for i in range(24):
        ts = (from_ts + timedelta(hours=i)).isoformat().replace("+00:00", "Z")
        verlauf.append(int(je_stunde.get(ts, {}).get("requests", 0)))
    return {
        "requests_24h": sum(verlauf) if punkte else None,
        "verlauf": verlauf,
        "fehler_5xx": sum(int(pt.get("status_5xx") or 0) for pt in punkte) if punkte else None,
    }


# ---------------------------------------------------------------------------
# Endpunkte
# ---------------------------------------------------------------------------


async def build_overview(session: Session) -> dict:
    """Ermittelt den kompletten Stand der Wand (wird vom Hintergrundlauf und bei Bedarf von der API genutzt)."""
    cfg = wc.load(session)
    hosts = [
        h for h in crud_hosts.list_hosts(session)
        if h.enabled and (not cfg.hosts or h.name in cfg.hosts)
    ]
    apps = crud_apps.list_apps(session)
    deploy_for_app: dict[str, dict] = {}
    for a in apps:
        d = crud_deployments.current_for_app(session, a.id)
        if d is not None:
            deploy_for_app[a.id] = {"ts": d.ts, "git_sha": (d.git_sha or "")[:7], "image": d.image, "status": d.status}

    async def per_host(h: HostRow) -> tuple[HostRow, dict, list[dict]]:
        erreichbar = h.is_self or h.last_status in ("online", "unknown")
        if not erreichbar:
            return h, {**host_stats._parse(""), "ok": False, "error": h.last_status, "ms": None}, []
        stats, projects = await asyncio.gather(
            asyncio.to_thread(host_stats.collect, h),
            asyncio.to_thread(docker_inspect.projects_on_host, h),
        )
        return h, stats, projects

    host_results = await asyncio.gather(*(per_host(h) for h in hosts), return_exceptions=True)

    hosts_out: list[dict] = []
    projects_out: list[dict] = []
    for h_cfg, res in zip(hosts, host_results, strict=False):
        if isinstance(res, BaseException):
            # Host bleibt sichtbar - mit Fehler statt stillschweigend verschwunden
            log.warning("Wand: Host-Abfrage %s fehlgeschlagen: %s", h_cfg.name, res)
            res = (h_cfg, {**host_stats._parse(""), "ok": False, "error": str(res)[:160], "ms": None}, [])
        h, stats, projects = res
        projekte = build_projects(h, projects, apps, cfg, deploy_for_app)
        projects_out.extend(projekte)
        hosts_out.append({
            "name": h.name,
            "ip": h.tailscale_ip,
            "description": h.description,
            "is_self": bool(h.is_self),
            "status": h.last_status,
            "last_check_at": h.last_check_at,
            "stats": stats,
            "tmux": stats.get("tmux") or [],
            "projects": [p["name"] for p in projekte],
            "project_count": len(projekte),
        })

    # Mehrwert-Sammler laufen nebeneinander: oeffentliche Dienste, Werkstatt je Host, Kira
    urls = list(dict.fromkeys([cfg.hero.get("url")] + [p["url"] for p in projects_out if p.get("url")] + list(cfg.links.values())))
    host_by_name = {h.name: h for h in hosts}
    erreichbar = {h["name"] for h in hosts_out if (h["stats"] or {}).get("ok")}
    werkstatt_tasks = [
        asyncio.to_thread(wx.werkstatt, host_by_name[name], work_dir, cfg.hide, int(cfg.werkstatt_aktiv_tage))
        for name, work_dir in cfg.work_dirs.items()
        if name in host_by_name and name in erreichbar and work_dir
    ]
    kira_host = host_by_name.get(str(cfg.kira.get("host") or ""))
    kira_task = (
        asyncio.to_thread(wx.kira, kira_host, cfg.kira, cfg.hide)
        if kira_host is not None and kira_host.name in erreichbar
        else asyncio.sleep(0, result={"ok": False, "total": None, "entries": [], "note": "Kira-Host nicht erreichbar", "host": cfg.kira.get("host")})
    )
    ki_host = host_by_name.get(str(cfg.ki_nutzung.get("host") or ""))
    ki_task = (
        asyncio.to_thread(kn.abfragen, ki_host, cfg.ki_nutzung)
        if ki_host is not None and ki_host.name in erreichbar
        else asyncio.sleep(0, result={"ok": False, "hinweis": "LLM-Host nicht erreichbar", "claude": {"verfuegbar": False}, "codex": {"verfuegbar": False}, "gemini": {"verfuegbar": False}})
    )
    fa_cfg = cfg.flow_agent or {}
    fa_task = asyncio.to_thread(
        fa.zustand, str(fa_cfg.get("url") or "https://agent.flowaudit.de"),
        _secret_value(session, str(fa_cfg.get("secret_key") or "flow_agent_read_key")),
        fa_cfg.get("hosts") if isinstance(fa_cfg.get("hosts"), dict) else {},
    )
    dienste_res, kira_out, ki_out, fa_out, *werkstatt_res = await asyncio.gather(
        wx.dienste_pruefen([u for u in urls if u]), kira_task, ki_task, fa_task, *werkstatt_tasks, return_exceptions=True
    )
    if not isinstance(fa_out, dict):
        log.warning("Wand: flow-agent fehlgeschlagen: %s", fa_out)
        fa_out = {"ok": False, "note": str(fa_out)[:120], "url": fa_cfg.get("url"), "hosts": [], "frische": {"status": "unknown", "healthy": 0, "degraded": 0, "unhealthy": 0, "befunde": []}, "meldungen": {"hosts_offline": [], "hosts_degraded": [], "pending_actions": 0, "failed_actions_recent": 0}, "version": None, "stand": None}
    if not isinstance(ki_out, dict):
        log.warning("Wand: KI-Nutzung fehlgeschlagen: %s", ki_out)
        ki_out = {"ok": False, "hinweis": str(ki_out)[:120], "claude": {"verfuegbar": False}, "codex": {"verfuegbar": False}, "gemini": {"verfuegbar": False}}
    dienste_out = dienste_res if isinstance(dienste_res, list) else []
    if not isinstance(kira_out, dict):
        log.warning("Wand: Kira-Abfrage fehlgeschlagen: %s", kira_out)
        kira_out = {"ok": False, "total": None, "entries": [], "note": str(kira_out)[:120], "host": cfg.kira.get("host")}
    werkstatt_out = [w for w in werkstatt_res if isinstance(w, dict)]
    for w in werkstatt_res:
        if isinstance(w, BaseException):
            log.warning("Wand: Werkstatt fehlgeschlagen: %s", w)
    for d in dienste_out:
        d.update(_zugriffe_24h(session, d["host"]))

    # GitHub: alle Repos + juengste Commits (nur mit Token)
    github_out: dict[str, Any] = {"enabled": github_client.is_enabled(), "repos": [], "commits": [], "error": None}
    commits: list[dict] = []
    if github_out["enabled"]:
        try:
            repos = [
                r for r in await asyncio.to_thread(github_client.list_user_repos, 100)
                if not wc.is_hidden(r["name"], cfg.hide)
            ]
            github_out["repos"] = repos
            recent = repos[:8]
            commit_lists = await asyncio.gather(
                *(asyncio.to_thread(github_client.list_repo_commits, r["owner"], r["name"], 4) for r in recent),
                return_exceptions=True,
            )
            for cl in commit_lists:
                if isinstance(cl, list):
                    commits.extend(cl)
            commits.sort(key=lambda c: c.get("date") or "", reverse=True)
            github_out["commits"] = commits[:25]
        except Exception as exc:  # noqa: BLE001 - GitHub darf die Wand nicht kippen
            github_out["error"] = str(exc)[:160]

    probes = await asyncio.gather(*(_run_probe(session, p) for p in cfg.probes), return_exceptions=True)
    probes_out = []
    for p, res in zip(cfg.probes, probes, strict=False):
        if isinstance(res, dict):
            probes_out.append(res)
        else:
            log.warning("Sonde %s: %s", p.get("id"), res)
            probes_out.append({"id": p.get("id"), "label": p.get("label"), "ok": False, "kpis": [], "note": str(res)[:120]})

    hero_proj = waehle_hero(projects_out, cfg.hero)
    hero_probe = next((p for p in probes_out if p.get("id") == cfg.hero.get("probe")), None)
    demo_cfg = cfg.demo
    demo_ready = bool(
        _secret_value(session, demo_cfg.get("user_secret")) and _secret_value(session, demo_cfg.get("password_secret"))
    )

    backups_out = _newest_backups(cfg.backup_dir)
    ai_router_out = await asyncio.to_thread(ai_router_client.status)
    geladen = set(ai_router_out.get("models") or [])
    ai_router_out["freigegeben"] = [m.get("label") or m.get("tag") for m in cfg.chat_models if m.get("tag") in geladen]
    alerts = wx.handlungsbedarf(
        hosts_out, projects_out, backups_out, dienste_out, ai_router_out, github_out, werkstatt_out,
        prod_hosts=cfg.prod_hosts,
    )
    alerts = sorted(alerts + kn.alarme(ki_out, float(cfg.ki_nutzung.get("warn_pct") or 85)) + fa.alarme(fa_out), key=lambda a: {"krit": 0, "warn": 1, "info": 2}.get(a["level"], 9))

    return {
        "generated_at": _iso_now(),
        "hosts": hosts_out,
        "projects": projects_out,
        "alerts": alerts,
        "dienste": dienste_out,
        "werkstatt": werkstatt_out,
        "kira": kira_out,
        "ki_nutzung": ki_out,
        "flow_agent": fa_out,
        "hero": {
            **cfg.hero,
            "project_state": hero_proj,
            "kpis": (hero_probe or {}).get("kpis", []),
            "probe_note": (hero_probe or {}).get("note"),
            "demo_ready": demo_ready,
        },
        "probes": probes_out,
        "backups": backups_out,
        "ai_router": ai_router_out,
        "github": github_out,
        "events": _events(session, commits),
        "links": cfg.links,
    }


@router.get("")
async def overview(
    frisch: bool = False, _=Depends(require_auth), session: Session = Depends(get_session)
) -> dict:
    """Letzter Stand des Hintergrundlaufs (sofort); mit ?frisch=1 oder ohne Stand wird neu ermittelt."""
    from ..services import wall_loop

    stand = None if frisch else wall_loop.letzter_stand(max_alter_s=150)
    if stand is None:
        stand = await wall_loop.stand_ermitteln()
    return stand


@router.get("/verlauf")
async def verlauf_lesen(
    hours: int = 24, keys: str | None = None, _=Depends(require_auth), session: Session = Depends(get_session)
) -> dict:
    """Zeitreihen der Wand: keys kommagetrennt (Vorgabe: Hero-Kennzahlen, Alarme, Host-Last)."""
    from ..services import verlauf

    hours = max(1, min(24 * 31, hours))
    if keys:
        wanted = [k.strip() for k in keys.split(",") if k.strip()][:60]
    else:
        alle = verlauf.keys(session)
        wanted = [k for k in alle if k.startswith("hero.") or k.startswith("alerts.") or k.endswith(".load1") or k.endswith(".gpu_pct") or k == "kira.total"]
    return {"hours": hours, "series": verlauf.series(session, wanted, hours=hours)}


_TMUX_ZIEL = re.compile(r"^[A-Za-z0-9_.-]{1,64}:[A-Za-z0-9_.-]{1,64}$")


class TmuxSenden(BaseModel):
    host: str = Field(min_length=1, max_length=64)
    ziel: str = Field(min_length=3, max_length=130)
    text: str = Field(min_length=1, max_length=2000)


def _tmux_host(session: Session, name: str) -> HostRow:
    from ..services.host_stats import _ziel

    host = next((h for h in crud_hosts.list_hosts(session) if h.name == name and h.enabled), None)
    if host is None:
        raise HTTPException(status_code=404, detail=f"Host „{name}“ unbekannt")
    return _ziel(host)


@router.get("/tmux/ausgabe")
async def tmux_ausgabe(
    host: str, ziel: str, zeilen: int = 40, _=Depends(require_auth), session: Session = Depends(get_session)
) -> dict:
    """Letzte Zeilen eines tmux-Fensters (capture-pane), nur lesend."""
    if not _TMUX_ZIEL.match(ziel):
        raise HTTPException(status_code=422, detail="Ziel muss die Form sitzung:fenster haben")
    zeilen = max(5, min(200, zeilen))
    h = _tmux_host(session, host)
    from ..services.ssh_runner import run_on_host

    cmd = f"tmux capture-pane -p -t {shlex.quote(ziel)} -S -{zeilen} 2>&1"
    res = await asyncio.to_thread(run_on_host, h, cmd, timeout=15)
    text = (res.stdout or res.stderr or "").rstrip("\n")
    return {"text": text[-12000:], "ok": res.ok}


@router.post("/tmux/senden")
async def tmux_senden(
    req: TmuxSenden, _=Depends(require_auth), session: Session = Depends(get_session)
) -> dict:
    """Arbeitspaket in ein tmux-Fenster tippen (send-keys) und mit Enter abschicken."""
    if not _TMUX_ZIEL.match(req.ziel):
        raise HTTPException(status_code=422, detail="Ziel muss die Form sitzung:fenster haben")
    text = "".join(ch for ch in req.text if ch == "\n" or ch >= " ").strip()
    if not text:
        raise HTTPException(status_code=422, detail="Leeres Arbeitspaket")
    h = _tmux_host(session, req.host)
    from ..services.ssh_runner import run_on_host

    # -l: Text woertlich (keine Tastennamen), danach Enter
    cmd = f"tmux send-keys -t {shlex.quote(req.ziel)} -l {shlex.quote(text)} && tmux send-keys -t {shlex.quote(req.ziel)} Enter"
    res = await asyncio.to_thread(run_on_host, h, cmd, timeout=15)
    crud_audit.write(session, action="wall.tmux_senden", target=f"{req.host}:{req.ziel}", after={"zeichen": len(text), "text": text[:300], "ok": res.ok})
    if not res.ok:
        raise HTTPException(status_code=502, detail=f"tmux: {(res.stderr or res.stdout or 'Fehler')[:160]}")
    return {"ok": True}


@router.post("/push-test")
async def push_test(_=Depends(require_auth), session: Session = Depends(get_session)) -> dict:
    """Schickt eine Testnachricht ueber den Push-Kanal (Telegram) – prueft Token, Chat und Weg."""

    cfg = wc.load(session)
    pcfg = cfg.push or {}
    token = _secret_value(session, str(pcfg.get("token_secret") or "telegram_bot_token"))
    chat_id = _secret_value(session, str(pcfg.get("chat_secret") or "telegram_chat_id")) or str(pcfg.get("chat_id") or "")
    if not token or not chat_id:
        raise HTTPException(status_code=409, detail="telegram_bot_token / telegram_chat_id fehlen im Vault")
    instanz = str(pcfg.get("instanz") or next((h.name for h in crud_hosts.list_hosts(session) if h.is_self), "Wand"))
    from ..services import wall_loop

    stand = wall_loop.letzter_stand() or {}
    alerts = [a for a in stand.get("alerts") or [] if a.get("level") in ("krit", "warn")]
    ok = await wall_loop.karte_senden(
        session, token, chat_id, instanz,
        alerts or [{"level": "info", "text": "Testnachricht – Push-Alarme sind eingerichtet", "hint": "Diese Karte kommt bei neuen Punkten ab „prüfen“"}],
        [], stand, cfg,
    )
    crud_audit.write(session, action="wall.push_test", target="telegram", after={"ok": ok})
    if not ok:
        raise HTTPException(status_code=502, detail="Telegram hat die Nachricht nicht angenommen (siehe Log)")
    return {"ok": True}


@router.get("/config")
async def get_config(_=Depends(require_auth), session: Session = Depends(get_session)) -> dict:
    return wc.load(session).as_dict()


@router.patch("/config")
async def patch_config(
    patch: dict, request_session=Depends(require_auth), session: Session = Depends(get_session)
) -> dict:
    before = wc.load(session).as_dict()
    cfg = wc.save(session, patch)
    crud_audit.write(session, action="wall.config", target="wall", before=before, after=cfg.as_dict())
    return cfg.as_dict()


class DemoStart(BaseModel):
    # neu=True erzwingt den Neuaufbau (bestehende Demo-Vorgaenge werden ersetzt - offene
    # Akten im Browser zeigen danach 404). Vorgabe: nur aufbauen, wenn die Demo unvollstaendig ist.
    neu: bool = False


@router.post("/demo")
async def demo_starten(
    payload: DemoStart | None = None, _=Depends(require_auth), session: Session = Depends(get_session)
) -> dict:
    """Stellt die HPP-Demo sicher: Anmeldung mit Vault-Zugang, Aufbau nur bei Bedarf (oder neu=True)."""
    cfg = wc.load(session)
    demo = cfg.demo
    user = _secret_value(session, demo.get("user_secret"))
    password = _secret_value(session, demo.get("password_secret"))
    if not user or not password:
        raise HTTPException(
            status_code=409,
            detail=(
                f"Zugangsdaten fehlen im Vault: Secrets „{demo.get('user_secret')}“ und "
                f"„{demo.get('password_secret')}“ anlegen (HPP-Benutzer mit Admin-Rolle)."
            ),
        )
    stand_url = demo.get("stand_url") or demo["aufbau_url"].rsplit("/aufbauen", 1)[0]
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(60.0, connect=10.0)) as c:
            login = await c.post(demo["login_url"], data={"username": user, "password": password})
            if login.status_code >= 400:
                raise HTTPException(status_code=502, detail=f"HPP-Anmeldung fehlgeschlagen (HTTP {login.status_code})")
            token = (login.json() or {}).get("access_token") if login.headers.get("content-type", "").startswith("application/json") else None
            if not token:
                raise HTTPException(status_code=502, detail="HPP-Anmeldung ohne access_token")
            kopf = {"Authorization": f"Bearer {token}"}
            neu = bool(payload and payload.neu)
            if not neu:
                # Demo schon vollstaendig? Dann nichts anfassen - sonst verlieren offene Akten ihre IDs.
                st = await c.get(stand_url, headers=kopf)
                if st.status_code < 400:
                    stand = st.json() or {}
                    faelle_soll = stand.get("faelle") or []
                    lauf = stand.get("aufbau") or {}
                    if faelle_soll and all(f.get("vorhanden") for f in faelle_soll) and not lauf.get("laeuft"):
                        faelle = [{"aktenzeichen": f.get("aktenzeichen"), "schritte": 0, "fehler": None} for f in faelle_soll]
                        return {
                            "ok": True, "uebersprungen": True, "faelle": faelle,
                            "url": f"{cfg.hero.get('url', '').rstrip('/')}{cfg.hero.get('demo_path', '')}",
                        }
            resp = await c.post(demo["aufbau_url"], json={}, headers=kopf)
            if resp.status_code == 409:
                # Aufbau laeuft bereits (z. B. zweiter Klick) - einfach mitwarten
                pass
            elif resp.status_code >= 400:
                raise HTTPException(status_code=502, detail=f"Demo-Aufbau fehlgeschlagen (HTTP {resp.status_code}): {resp.text[:200]}")
            ergebnis = resp.json() if resp.status_code < 400 else {}
            if not isinstance(ergebnis, dict):
                raise HTTPException(status_code=502, detail="Demo-Aufbau: unerwartete Antwort von HPP")
            if resp.status_code in (202, 409) or ergebnis.get("gestartet") is True:
                # Hintergrund-Aufbau: Fortschritt abfragen, bis er beendet ist (Tunnel-Limit 100 s umgangen)
                start = time.monotonic()
                ergebnis = {}
                while time.monotonic() - start < 600:
                    await asyncio.sleep(5)
                    st = await c.get(stand_url, headers=kopf)
                    if st.status_code >= 400:
                        continue
                    lauf = (st.json() or {}).get("aufbau") or {}
                    if lauf and not lauf.get("laeuft"):
                        if lauf.get("fehler"):
                            raise HTTPException(status_code=502, detail=f"Demo-Aufbau fehlgeschlagen: {lauf['fehler'][:200]}")
                        ergebnis = lauf.get("ergebnis") or {}
                        break
                else:
                    raise HTTPException(status_code=504, detail="Demo-Aufbau nach 10 Minuten nicht beendet")
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"HPP nicht erreichbar: {exc}") from exc
    faelle = [
        {"aktenzeichen": f.get("aktenzeichen"), "schritte": len(f.get("schritte") or []), "fehler": f.get("fehler")}
        for f in ergebnis.get("faelle", [])
    ]
    crud_audit.write(session, action="wall.demo_start", target=demo.get("aufbau_url"), after={"faelle": faelle, "neu": bool(payload and payload.neu)})
    return {
        "ok": bool(faelle) and all(not f["fehler"] for f in faelle),
        "uebersprungen": False,
        "faelle": faelle,
        "url": f"{cfg.hero.get('url', '').rstrip('/')}{cfg.hero.get('demo_path', '')}",
    }
