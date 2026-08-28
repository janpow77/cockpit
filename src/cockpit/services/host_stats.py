"""Leichte Host-Kennzahlen fuer die Wand (Load, RAM, Disk, Uptime, Container).

Ein einziger Shell-Befehl je Host (via ssh_runner), Ergebnis 45 s gecacht,
damit die Wand alle 30 s pollen kann, ohne jeden Host jedes Mal per SSH
anzufassen. Auf dem Self-Host laeuft der Befehl im Container: /proc/loadavg,
/proc/meminfo und /proc/uptime zeigen dort die Werte des Hosts; die Platte
wird ueber das /data-Bind-Mount gemessen (Fallback: /).
"""

from __future__ import annotations

import logging
import threading
import time

from ..models import HostRow
from .ssh_runner import run_on_host

log = logging.getLogger(__name__)

CACHE_TTL_S = 45
_cache: dict[str, tuple[float, dict]] = {}
_lock = threading.Lock()

# Jede Zeile ein Messwert; Fehler einzelner Teile duerfen den Rest nicht kippen.
# Linux liest /proc, macOS (Vorfuehrrechner) sysctl/vm_stat - beide liefern dieselben Zeilen.
_CMD_LINUX = (
    "cat /proc/loadavg 2>/dev/null | awk '{print \"load\", $1, $2, $3}'; "
    "awk '/MemTotal/{t=$2} /MemAvailable/{a=$2} END{print \"mem\", int(t/1024), int((t-a)/1024)}' /proc/meminfo 2>/dev/null; "
    "awk '{print \"uptime\", int($1)}' /proc/uptime 2>/dev/null; "
    "echo cpus $(nproc 2>/dev/null || echo 0)"
)
_CMD_MAC = (
    "sysctl -n vm.loadavg 2>/dev/null | tr ',' '.' | awk '{print \"load\", $2, $3, $4}'; "
    "ps=$(sysctl -n hw.pagesize 2>/dev/null || echo 16384); t=$(sysctl -n hw.memsize 2>/dev/null || echo 0); "
    "vm_stat 2>/dev/null | tr -d '.' | awk -v ps=\"$ps\" -v t=\"$t\" "
    "'/Pages active/{a=$3} /Pages wired/{w=$4} /occupied by compressor/{c=$5} END{print \"mem\", int(t/1048576), int((a+w+c)*ps/1048576)}'; "
    "b=$(sysctl -n kern.boottime 2>/dev/null | sed -n 's/^{ sec = \\([0-9]*\\),.*/\\1/p'); "
    "[ -n \"$b\" ] && echo uptime $(( $(date +%s) - b )); "
    "echo cpus $(sysctl -n hw.ncpu 2>/dev/null || echo 0)"
)
_CMD = (
    # zsh (macOS) bricht bei leeren Globs ab - nonomatch schaltet das ab; bash ignoriert den Befehl
    "setopt nonomatch 2>/dev/null; "
    f"if [ -r /proc/loadavg ]; then {_CMD_LINUX}; else {_CMD_MAC}; fi; "
    "(df -P /data 2>/dev/null || df -P / 2>/dev/null) | awk 'NR==2{print \"disk\", $2, $3, $5}'; "
    "if command -v docker >/dev/null 2>&1; then echo containers $(docker ps -q 2>/dev/null | wc -l); else echo containers 0; fi; "
    # GPUs: NVIDIA ueber nvidia-smi, AMD ueber sysfs (nur Auslastung)
    "if command -v nvidia-smi >/dev/null 2>&1; then nvidia-smi --query-gpu=utilization.gpu,memory.used,memory.total --format=csv,noheader,nounits 2>/dev/null "
    "| awk -F', *' '{print \"gpu\", $1, $2, $3}'; "
    "elif [ -d /sys/class/drm ]; then for d in /sys/class/drm/card*/device; do [ -r \"$d/gpu_busy_percent\" ] || continue; "
    "u=$(cat \"$d/mem_info_vram_used\" 2>/dev/null || echo 0); t=$(cat \"$d/mem_info_vram_total\" 2>/dev/null || echo 0); "
    "echo gpu $(cat \"$d/gpu_busy_percent\") $((u/1048576)) $((t/1048576)); done 2>/dev/null; fi; "
    # tmux-Sitzungen des SSH-Nutzers: je Fenster eine Tab-getrennte Zeile
    # Kein tmux-Server ist kein Fehler: Exit-Code der Sonde bleibt 0
    "tmux list-windows -a -F 'tmuxw\t#{session_name}\t#{window_name}\t#{window_active}\t#{pane_current_command}\t#{session_attached}\t#{session_created}' 2>/dev/null || true; true"
)


def _parse(stdout: str) -> dict:
    out: dict = {
        "load1": None, "load5": None, "load15": None, "cpus": None,
        "mem_total_mb": None, "mem_used_mb": None, "mem_pct": None,
        "disk_total_kb": None, "disk_used_kb": None, "disk_pct": None,
        "uptime_s": None, "containers": None, "gpus": [], "tmux": [],
    }
    sitzungen: dict[str, dict] = {}
    for line in stdout.splitlines():
        if line.startswith("tmuxw\t"):
            teile = line.split("\t")
            if len(teile) >= 7:
                _, sitzung, fenster, aktiv, cmd, attached, created = teile[:7]
                eintrag = sitzungen.setdefault(sitzung, {"name": sitzung, "attached": False, "created": None, "windows": []})
                eintrag["attached"] = eintrag["attached"] or attached not in ("", "0")
                try:
                    eintrag["created"] = int(created)
                except ValueError:
                    pass
                eintrag["windows"].append({"name": fenster, "active": aktiv == "1", "cmd": cmd})
            continue
        parts = line.split()
        if not parts:
            continue
        key, vals = parts[0], parts[1:]
        try:
            if key == "load" and len(vals) >= 3:
                out["load1"], out["load5"], out["load15"] = float(vals[0]), float(vals[1]), float(vals[2])
            elif key == "mem" and len(vals) >= 2:
                total, used = int(vals[0]), int(vals[1])
                out["mem_total_mb"], out["mem_used_mb"] = total, used
                out["mem_pct"] = round(used * 100 / total, 1) if total else None
            elif key == "disk" and len(vals) >= 3:
                out["disk_total_kb"], out["disk_used_kb"] = int(vals[0]), int(vals[1])
                out["disk_pct"] = float(vals[2].rstrip("%"))
            elif key == "uptime" and vals:
                out["uptime_s"] = int(vals[0])
            elif key == "cpus" and vals:
                out["cpus"] = int(vals[0]) or None
            elif key == "containers" and vals:
                out["containers"] = int(vals[0])
            elif key == "gpu" and vals:
                out["gpus"].append({
                    "util_pct": int(float(vals[0])),
                    "mem_used_mb": int(float(vals[1])) if len(vals) > 1 else None,
                    "mem_total_mb": int(float(vals[2])) if len(vals) > 2 else None,
                })
        except ValueError:
            continue
    out["tmux"] = list(sitzungen.values())
    return out


def _ziel(host: HostRow) -> HostRow:
    """Self-Host mit SSH-Zugang: per Loopback-SSH abfragen, damit tmux und Nutzerumgebung
    des Hosts sichtbar sind (im Container gibt es beides nicht)."""
    if host.is_self and getattr(host, "ssh_user", None) and getattr(host, "tailscale_ip", None):
        import os
        from types import SimpleNamespace

        # Im Bridge-Netz (Hetzner) ist die Tailscale-IP des eigenen Hosts nicht erreichbar -
        # COCKPIT_SELF_SSH_HOST (z. B. host.docker.internal) zeigt dann auf das Host-Gateway.
        ziel_ip = os.environ.get("COCKPIT_SELF_SSH_HOST") or host.tailscale_ip
        werte = {k: getattr(host, k) for k in ("id", "name", "ssh_user", "ssh_key_path")}
        return SimpleNamespace(**werte, tailscale_ip=ziel_ip, is_self=0)  # type: ignore[return-value]
    return host


def collect(host: HostRow, *, refresh: bool = False) -> dict:
    """Kennzahlen eines Hosts; bei Fehler {"ok": False, "error": ...} mit leeren Werten."""
    now = time.time()
    with _lock:
        cached = _cache.get(host.id)
    if cached and not refresh and now - cached[0] < CACHE_TTL_S:
        return cached[1]
    try:
        ziel = _ziel(host)
        try:
            result = run_on_host(ziel, _CMD, timeout=12)
            if not result.ok and ziel is not host:
                raise RuntimeError(result.stderr or f"rc={result.exit_code}")
        except Exception:
            if ziel is host:
                raise
            result = run_on_host(host, _CMD, timeout=12)  # Loopback nicht moeglich: lokal im Container
    except Exception as exc:  # noqa: BLE001 - Wand darf nie an einem Host scheitern
        data = {**_parse(""), "ok": False, "error": str(exc)[:160], "ms": None}
    else:
        data = _parse(result.stdout)
        data["ok"] = result.ok
        data["error"] = None if result.ok else (result.stderr or f"rc={result.exit_code}")[:160]
        data["ms"] = result.duration_ms
    with _lock:
        _cache[host.id] = (now, data)
    return data
