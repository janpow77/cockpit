"""Health-Check-Loop fuer Hosts und Apps.

- Hosts: ping + ssh-test (per CommandResult)
- Apps: docker_inspect.summarize_app + optional HTTP-healthcheck
"""
from __future__ import annotations

import asyncio
import logging
import time

import httpx

from ..crud import apps as crud_apps
from ..crud import hosts as crud_hosts
from ..db import get_session_factory
from ..models import AppRow, HostRow
from . import docker_inspect, tailscale
from .ssh_runner import ping_host

log = logging.getLogger(__name__)


async def _http_health(url: str, timeout: float = 4.0) -> dict:
    try:
        async with httpx.AsyncClient(timeout=timeout) as c:
            resp = await c.get(url)
        return {"ok": 200 <= resp.status_code < 400, "status": resp.status_code}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)[:200]}


def check_host(session, host: HostRow) -> dict:
    """Prueft einen Host: SSH-erreichbar + Tailscale-online."""
    ts_peers = tailscale.peer_status_by_ip()
    ts_info = ts_peers.get(host.tailscale_ip) or {}
    ssh = ping_host(host, timeout=5)

    if host.is_self:
        status = "online" if ssh.ok else "unreachable"
    elif ssh.ok:
        status = "online"
    elif ts_info.get("online"):
        status = "ssh-down"
    else:
        status = "offline" if not ts_info else "unreachable"

    err = None if ssh.ok else (ssh.stderr or f"rc={ssh.exit_code}")[:200]
    crud_hosts.update_status(session, host.id, status=status, error=err)
    return {"status": status, "tailscale": ts_info, "ssh": {"ok": ssh.ok, "ms": ssh.duration_ms}}


def check_app(session, app: AppRow, host: HostRow) -> dict:
    """Prueft eine App: Container-Inspect + optional HTTP-Health."""
    summary = docker_inspect.summarize_app(host, filter_expr=app.container_filter or f"name={app.name}")
    http_info: dict | None = None
    if app.healthcheck_url:
        try:
            http_info = asyncio.run(_http_health(app.healthcheck_url))
        except RuntimeError:
            # Already in loop — use sync fallback
            try:
                with httpx.Client(timeout=4.0) as c:
                    r = c.get(app.healthcheck_url)
                http_info = {"ok": 200 <= r.status_code < 400, "status": r.status_code}
            except Exception as exc:  # noqa: BLE001
                http_info = {"ok": False, "error": str(exc)[:200]}

    final = summary["status"]
    if http_info is not None:
        if not http_info.get("ok"):
            final = "degraded" if final == "healthy" else final
    crud_apps.update_status(session, app.id, status=final, summary={
        "container_count": summary["container_count"],
        "healthy_count": summary["healthy_count"],
        "http": http_info,
    })
    return {**summary, "http": http_info, "status": final}


async def health_loop(stop_event: asyncio.Event, *, interval_s: int = 60) -> None:
    """Background-Loop fuer Hosts + Apps."""
    log.info("Health-Loop gestartet (interval=%ds).", interval_s)
    while not stop_event.is_set():
        try:
            await asyncio.to_thread(_run_once)
        except Exception as exc:
            log.warning("Health-Loop iteration error: %s", exc)
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=interval_s)
        except TimeoutError:
            pass
    log.info("Health-Loop beendet.")


def _run_once() -> None:
    factory = get_session_factory()
    with factory() as session:
        hosts = crud_hosts.list_hosts(session)
        for h in hosts:
            if not h.enabled:
                continue
            try:
                check_host(session, h)
            except Exception as exc:
                log.warning("check_host(%s) error: %s", h.name, exc)
        apps = crud_apps.list_apps(session)
        host_by_id: dict[str, HostRow] = {h.id: h for h in hosts}
        for app in apps:
            if not app.enabled:
                continue
            host = host_by_id.get(app.host_id)
            if host is None or not host.enabled:
                continue
            if host.last_status not in ("online", "unknown"):
                # Host nicht erreichbar — App-Status auf unknown lassen
                continue
            try:
                check_app(session, app, host)
            except Exception as exc:
                log.warning("check_app(%s/%s) error: %s", host.name, app.name, exc)


def started_recently_seconds() -> int:
    return int(time.time())
