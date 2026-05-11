"""Tailscale-Status (lokal). Cache 30s.

Funktioniert nur, wenn `tailscale` im Container-PATH oder via Volume erreichbar ist.
Im Cockpit-Container ist tailscale typischerweise NICHT installiert — wir
laufen als Sidecar zur Host-Tailscale-Bindung. Daher ein zweites Fallback:
Wenn `tailscale` nicht da ist, geben wir die in der DB gepflegten Hosts zurueck
mit status=unknown.
"""
from __future__ import annotations

import json
import logging
import subprocess
import threading
import time

log = logging.getLogger(__name__)

CACHE_TTL_S = 30

_cache: dict | None = None
_cache_ts: float = 0.0
_lock = threading.Lock()


def status(refresh: bool = False) -> dict:
    """Liefert das tailscale-status JSON oder ein synthetisches dict mit error."""
    global _cache, _cache_ts
    now = time.time()
    with _lock:
        if not refresh and _cache and (now - _cache_ts) < CACHE_TTL_S:
            return _cache

    try:
        proc = subprocess.run(
            ["tailscale", "status", "--json"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if proc.returncode != 0:
            data = {"error": f"tailscale exit {proc.returncode}", "stderr": proc.stderr[:200], "Peer": {}, "Self": {}}
        else:
            try:
                data = json.loads(proc.stdout)
            except json.JSONDecodeError as exc:
                data = {"error": f"json parse: {exc}", "Peer": {}, "Self": {}}
    except FileNotFoundError:
        data = {"error": "tailscale binary nicht gefunden", "Peer": {}, "Self": {}}
    except subprocess.TimeoutExpired:
        data = {"error": "tailscale status timeout", "Peer": {}, "Self": {}}

    with _lock:
        _cache = data
        _cache_ts = time.time()
    return data


def peer_status_by_ip() -> dict[str, dict]:
    """Map IP → {hostname, online, last_seen, os}."""
    raw = status()
    out: dict[str, dict] = {}

    self_block = raw.get("Self") or {}
    if self_block:
        for ip in self_block.get("TailscaleIPs", []) or []:
            out[str(ip)] = {
                "hostname": self_block.get("HostName") or self_block.get("DNSName", ""),
                "online": True,
                "last_seen": "now",
                "os": self_block.get("OS", ""),
                "is_self": True,
            }

    peers = raw.get("Peer") or {}
    for _, peer in peers.items():
        ips = peer.get("TailscaleIPs", []) or []
        for ip in ips:
            out[str(ip)] = {
                "hostname": peer.get("HostName") or peer.get("DNSName", ""),
                "online": bool(peer.get("Online")),
                "last_seen": peer.get("LastSeen", ""),
                "os": peer.get("OS", ""),
                "is_self": False,
            }
    return out
