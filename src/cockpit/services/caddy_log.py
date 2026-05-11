"""Caddy-Access-Log Parser + Aggregator.

Caddy schreibt JSON-Lines, ein Request pro Zeile. Beispiel-Schluessel:

    {"ts": 1715420400.123, "request": {"host": "workshop.flowaudit.de",
     "uri": "/api/system/ollama", "method": "GET"},
     "status": 200, "size": 1234, "duration": 0.042}

Wir aggregieren auf 1-Minuten-Buckets pro (host_id, server_name, app_id) und
schreiben in ``cockpit_traffic_samples``.
"""
from __future__ import annotations

import json
import logging
import statistics
from collections import defaultdict
from datetime import UTC, datetime
from typing import Iterator

log = logging.getLogger(__name__)


def _bucket_minute(ts: float) -> str:
    """Rundet Unix-Timestamp auf volle Minute (UTC) und gibt ISO8601 zurueck."""
    dt = datetime.fromtimestamp(int(ts // 60) * 60, tz=UTC)
    return dt.isoformat().replace("+00:00", "Z")


def parse_lines(lines: Iterator[str]) -> Iterator[dict]:
    """Parst Caddy-JSON-Lines. Liefert nur valide Request-Eintraege."""
    for raw in lines:
        raw = raw.strip()
        if not raw or raw.startswith("#"):
            continue
        try:
            obj = json.loads(raw)
        except (ValueError, TypeError):
            continue
        # Caddy schreibt request-Logs unter logger="http.log.access" — wir
        # akzeptieren alles mit status + request.host.
        req = obj.get("request") or {}
        host = req.get("host") or req.get("server_name") or obj.get("host")
        status = obj.get("status")
        ts = obj.get("ts")
        if host is None or status is None or ts is None:
            continue
        # Caddy-`ts` ist float-Sekunden. Bei aelteren Versionen ein String —
        # dann ueberspringen, statt zu raten.
        try:
            ts_float = float(ts)
        except (TypeError, ValueError):
            continue
        yield {
            "ts": ts_float,
            "host": host.lower(),
            "status": int(status),
            "size": int(obj.get("size") or 0),
            "duration": float(obj.get("duration") or 0.0),
            "uri": req.get("uri") or "",
            "method": req.get("method") or "",
        }


def aggregate(entries: Iterator[dict]) -> dict[tuple[str, str], dict]:
    """Aggregiert geparste Requests auf (bucket, server_name)-Schluessel.

    Returns dict mit:
        {"requests": int, "status_2xx": int, ..., "bytes_out": int,
         "latencies": [int]}  -- Latenzen in Millisekunden, fuer Percentile.
    """
    buckets: dict[tuple[str, str], dict] = defaultdict(
        lambda: {
            "requests": 0,
            "status_2xx": 0, "status_3xx": 0, "status_4xx": 0, "status_5xx": 0,
            "bytes_out": 0,
            "latencies": [],
        },
    )
    for e in entries:
        key = (_bucket_minute(e["ts"]), e["host"])
        b = buckets[key]
        b["requests"] += 1
        sc = e["status"]
        if 200 <= sc < 300:
            b["status_2xx"] += 1
        elif 300 <= sc < 400:
            b["status_3xx"] += 1
        elif 400 <= sc < 500:
            b["status_4xx"] += 1
        elif 500 <= sc < 600:
            b["status_5xx"] += 1
        b["bytes_out"] += e["size"]
        # duration ist Sekunden → ms, gerundet
        b["latencies"].append(int(e["duration"] * 1000))
    return buckets


def percentiles(latencies: list[int]) -> tuple[int | None, int | None, int | None]:
    """Berechnet (p50, p95, max). Gibt (None, None, None) bei leerer Liste."""
    if not latencies:
        return (None, None, None)
    if len(latencies) == 1:
        v = latencies[0]
        return (v, v, v)
    sorted_l = sorted(latencies)
    p50_idx = (len(sorted_l) - 1) // 2
    p95_idx = max(0, int(round((len(sorted_l) - 1) * 0.95)))
    return (
        int(statistics.median(sorted_l)),
        int(sorted_l[p95_idx]),
        int(sorted_l[-1]),
    )


def resolve_app_id(
    server_name: str,
    server_app_map: list[dict],
    app_name_to_id: dict[str, str],
) -> str | None:
    """Findet die zugeordnete App-ID anhand des Caddy-Hostnames."""
    for entry in server_app_map:
        if not isinstance(entry, dict):
            continue
        sn = (entry.get("server_name") or "").lower()
        an = entry.get("app_name") or ""
        if sn == server_name.lower():
            return app_name_to_id.get(an)
    return None
