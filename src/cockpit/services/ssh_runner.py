"""SSH-Runner via paramiko + lokale subprocess fuer is_self-Hosts.

API:
    run_on_host(host, "docker ps") -> CommandResult

CommandResult ist ein simples Dataclass mit (exit_code, stdout, stderr, duration_ms).

Defaults:
- Connect-Timeout 5s
- Command-Timeout via Param (default 30s)
- Connection-Cache pro (host_name, user, key_path) — 10 Eintraege max
"""
from __future__ import annotations

import logging
import os
import shutil
import subprocess
import threading
import time
from dataclasses import dataclass

import paramiko

from ..models import HostRow

log = logging.getLogger(__name__)

CONNECT_TIMEOUT_S = 5
DEFAULT_CMD_TIMEOUT_S = 30


@dataclass
class CommandResult:
    exit_code: int
    stdout: str
    stderr: str
    duration_ms: int

    @property
    def ok(self) -> bool:
        return self.exit_code == 0


class _ConnectionPool:
    """Sehr kleiner Connection-Cache. Stale Connections werden best-effort
    erkannt (try-recover beim naechsten Use). Kein TTL — Container-Lifetime."""

    def __init__(self, max_size: int = 10):
        self._lock = threading.Lock()
        self._cache: dict[tuple, paramiko.SSHClient] = {}
        self._max = max_size

    def _key(self, host: HostRow) -> tuple:
        return (host.name, host.ssh_user or "janpow", host.ssh_key_path or "")

    def get(self, host: HostRow) -> paramiko.SSHClient:
        key = self._key(host)
        with self._lock:
            client = self._cache.get(key)
            if client is not None:
                # Sanity-Check: transport active?
                t = client.get_transport()
                if t and t.is_active():
                    return client
                else:
                    try:
                        client.close()
                    except Exception:
                        pass
                    self._cache.pop(key, None)
            client = self._connect(host)
            if len(self._cache) >= self._max:
                # einfaches FIFO-Evict
                try:
                    old_key, old_client = next(iter(self._cache.items()))
                    old_client.close()
                    self._cache.pop(old_key, None)
                except Exception:
                    pass
            self._cache[key] = client
            return client

    def _connect(self, host: HostRow) -> paramiko.SSHClient:
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        kwargs: dict = {
            "hostname": host.tailscale_ip,
            "username": host.ssh_user or "janpow",
            "timeout": CONNECT_TIMEOUT_S,
            "banner_timeout": CONNECT_TIMEOUT_S,
            "auth_timeout": CONNECT_TIMEOUT_S,
            "look_for_keys": True,
            "allow_agent": True,
        }
        if host.ssh_key_path:
            key_path = os.path.expanduser(host.ssh_key_path)
            if os.path.exists(key_path):
                kwargs["key_filename"] = key_path
            else:
                log.warning("SSH-Key nicht gefunden: %s — fallback auf agent/default", key_path)
        client.connect(**kwargs)
        log.info("SSH connected: %s@%s", kwargs["username"], host.tailscale_ip)
        return client

    def invalidate(self, host: HostRow) -> None:
        key = self._key(host)
        with self._lock:
            client = self._cache.pop(key, None)
        if client:
            try:
                client.close()
            except Exception:
                pass


_pool = _ConnectionPool()


def _run_local(command: str, timeout: int) -> CommandResult:
    """Fuer is_self-Host: lokale subprocess."""
    t0 = time.monotonic()
    try:
        proc = subprocess.run(
            ["bash", "-lc", command],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        dur = int((time.monotonic() - t0) * 1000)
        return CommandResult(
            exit_code=proc.returncode,
            stdout=proc.stdout or "",
            stderr=proc.stderr or "",
            duration_ms=dur,
        )
    except subprocess.TimeoutExpired:
        dur = int((time.monotonic() - t0) * 1000)
        return CommandResult(exit_code=124, stdout="", stderr="Timeout", duration_ms=dur)
    except FileNotFoundError as exc:
        dur = int((time.monotonic() - t0) * 1000)
        return CommandResult(exit_code=127, stdout="", stderr=f"shell missing: {exc}", duration_ms=dur)


def run_on_host(host: HostRow, command: str, *, timeout: int = DEFAULT_CMD_TIMEOUT_S) -> CommandResult:
    """Fuehrt einen Shell-Befehl auf dem Host aus.

    is_self → lokal via subprocess. Sonst SSH via paramiko.
    """
    if host.is_self:
        return _run_local(command, timeout=timeout)

    t0 = time.monotonic()
    try:
        client = _pool.get(host)
        stdin, stdout, stderr = client.exec_command(command, timeout=timeout)
        out = stdout.read().decode("utf-8", errors="replace")
        err = stderr.read().decode("utf-8", errors="replace")
        rc = stdout.channel.recv_exit_status()
        dur = int((time.monotonic() - t0) * 1000)
        return CommandResult(exit_code=rc, stdout=out, stderr=err, duration_ms=dur)
    except (paramiko.SSHException, OSError, EOFError) as exc:
        dur = int((time.monotonic() - t0) * 1000)
        log.warning("SSH-Fehler auf %s: %s", host.name, exc)
        _pool.invalidate(host)
        return CommandResult(exit_code=255, stdout="", stderr=str(exc), duration_ms=dur)


def ping_host(host: HostRow, *, timeout: int = 5) -> CommandResult:
    """Test ob der Host erreichbar ist. Bei is_self lokales `true`, sonst SSH `true`."""
    if host.is_self:
        return _run_local("true", timeout=timeout)
    return run_on_host(host, "echo cockpit-ssh-ok", timeout=timeout)


def has_local_command(name: str) -> bool:
    return shutil.which(name) is not None
