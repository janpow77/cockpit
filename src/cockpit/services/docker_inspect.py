"""Docker-Container-Inspect ueber SSH.

Cache pro (host_id, filter) fuer 30s.
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

CACHE_TTL_S = 30

# In-Memory-Cache: { (host_id, filter): (ts, list_of_containers) }
_cache: dict[tuple[str, str], tuple[float, list[dict]]] = {}
_cache_lock = threading.Lock()


def _cached(host_id: str, filter_expr: str) -> list[dict] | None:
    with _cache_lock:
        entry = _cache.get((host_id, filter_expr))
    if entry is None:
        return None
    ts, data = entry
    if time.time() - ts > CACHE_TTL_S:
        return None
    return data


def _store(host_id: str, filter_expr: str, data: list[dict]) -> None:
    with _cache_lock:
        _cache[(host_id, filter_expr)] = (time.time(), data)


def invalidate_cache(host_id: str | None = None) -> None:
    with _cache_lock:
        if host_id is None:
            _cache.clear()
        else:
            for k in list(_cache.keys()):
                if k[0] == host_id:
                    _cache.pop(k, None)


def list_containers(host: HostRow, *, filter_expr: str = "", refresh: bool = False) -> list[dict]:
    """Listet Container auf dem Host. Filter = docker ps --filter Wert (z.B. "name=auditworkshop-")."""
    if not refresh:
        cached = _cached(host.id, filter_expr)
        if cached is not None:
            return cached

    cmd = "docker ps -a --no-trunc --format '{{json .}}'"
    if filter_expr:
        # docker ps unterstuetzt mehrere --filter; wir nehmen einen
        cmd = f"docker ps -a --no-trunc --filter {shlex.quote(filter_expr)} --format '{{{{json .}}}}'"

    result = run_on_host(host, cmd, timeout=15)
    if not result.ok:
        log.warning("docker ps fehlgeschlagen auf %s: rc=%d err=%s", host.name, result.exit_code, result.stderr[:200])
        empty: list[dict] = []
        _store(host.id, filter_expr, empty)
        return empty

    containers: list[dict] = []
    for line in result.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
            containers.append({
                "name": obj.get("Names", ""),
                "image": obj.get("Image", ""),
                "state": obj.get("State", ""),
                "status": obj.get("Status", ""),
                "ports": obj.get("Ports", ""),
                "id": obj.get("ID", ""),
            })
        except (json.JSONDecodeError, AttributeError):
            continue
    _store(host.id, filter_expr, containers)
    return containers


def summarize_app(host: HostRow, *, filter_expr: str) -> dict:
    """Liefert {container_count, healthy_count, status, containers}."""
    containers = list_containers(host, filter_expr=filter_expr)
    cnt = len(containers)
    healthy = sum(1 for c in containers if c["state"] == "running")
    if cnt == 0:
        status = "unknown"
    elif healthy == cnt:
        status = "healthy"
    elif healthy == 0:
        status = "down"
    else:
        status = "degraded"
    return {
        "container_count": cnt,
        "healthy_count": healthy,
        "status": status,
        "containers": containers,
    }


def restart_app(host: HostRow, *, compose_path: str | None, container_filter: str) -> dict:
    """Compose-Restart oder Container-by-Filter-Restart. Liefert {ok, log, error}."""
    if compose_path:
        cmd = f"cd {shlex.quote(compose_path.rsplit('/', 1)[0])} && docker compose -f {shlex.quote(compose_path)} restart"
        result = run_on_host(host, cmd, timeout=120)
    elif container_filter:
        # Reihenfolge: list -> restart pro container
        cmd = (
            f"docker ps --filter {shlex.quote(container_filter)} -q | xargs -r docker restart"
        )
        result = run_on_host(host, cmd, timeout=120)
    else:
        return {"ok": False, "log": "", "error": "Weder compose_path noch container_filter gesetzt"}

    invalidate_cache(host.id)
    return {
        "ok": result.ok,
        "log": (result.stdout + result.stderr)[-2000:],
        "error": None if result.ok else (result.stderr or f"rc={result.exit_code}")[:200],
    }


def fetch_logs(
    host: HostRow,
    *,
    compose_path: str | None,
    container_filter: str,
    tail: int = 200,
) -> str:
    """Holt Logs. Bei compose_path: docker compose logs --tail N. Sonst pro Container."""
    tail = max(1, min(tail, 5000))
    if compose_path:
        cmd = (
            f"docker compose -f {shlex.quote(compose_path)} logs --no-color --tail {tail} 2>&1 | tail -n {tail}"
        )
        result = run_on_host(host, cmd, timeout=30)
        return result.stdout if result.ok else f"[error] {result.stderr or 'rc=' + str(result.exit_code)}"
    elif container_filter:
        cmd = (
            f"docker ps --filter {shlex.quote(container_filter)} --format '{{{{.Names}}}}' "
            f"| while read n; do echo '=== '$n' ==='; docker logs --tail {tail} \"$n\" 2>&1; done"
        )
        result = run_on_host(host, cmd, timeout=30)
        return result.stdout if result.ok else f"[error] {result.stderr}"
    else:
        return "[no compose_path / no container_filter — kann keine Logs holen]"
