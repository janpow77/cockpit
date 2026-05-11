"""Traffic-Collector: pollt Caddy-Logs auf Hosts und schreibt Aggregate.

Pull-Modell: 1× pro Minute laeuft ``collect_once()`` und fragt jeden
registrierten ``cockpit_traffic_sources``-Eintrag ab. Per SSH wird der neu
hinzugekommene Teil der Logfile geholt (Byte-Offset-Tail), in
``caddy_log.aggregate()`` zerlegt und in ``cockpit_traffic_samples``
geupsertet.

Logrotation wird per Inode-Vergleich erkannt (``stat -c %i`` ueber SSH):
wechselt der Inode, beginnen wir bei Offset 0 des neuen File.
"""
from __future__ import annotations

import asyncio
import json
import logging
import uuid
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from ..db import get_session_factory
from ..models import (
    AppRow,
    HostRow,
    TrafficSampleRow,
    TrafficSourceRow,
)
from . import caddy_log, ssh_runner

log = logging.getLogger(__name__)

# Maximal so viele Bytes pro Lauf einlesen (verhindert Speicher-Explosion
# beim ersten Lauf nach grosser Pause oder bei sehr verbose-Logs).
MAX_BYTES_PER_RUN = 20 * 1024 * 1024  # 20 MB


def _now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _ssh_tail(host: HostRow, log_path: str, offset: int) -> tuple[str, str, int]:
    """Liest neu hinzugekommene Bytes via SSH. Gibt (inhalt, inode, neuer_offset) zurueck.

    Strategie:
    1. ``stat -c '%i %s'`` → Inode + Groesse
    2. Wenn Inode != letzter Inode → Offset auf 0 (Rotation)
    3. Wenn Groesse < Offset → Offset auf 0 (truncation)
    4. ``tail -c +$((offset + 1)) -c $((MAX_BYTES_PER_RUN))`` → neue Bytes
    """
    stat = ssh_runner.run_on_host(
        host,
        f"stat -c '%i %s' {log_path!s}",
        timeout=10,
    )
    if stat.exit_code != 0:
        raise RuntimeError(f"stat failed: {stat.stderr.strip() or stat.exit_code}")
    parts = stat.stdout.strip().split()
    if len(parts) != 2:
        raise RuntimeError(f"unerwarteter stat-output: {stat.stdout!r}")
    inode, size_s = parts
    size = int(size_s)

    start = offset
    if start > size:
        # Truncation oder Rotation ohne Inode-Wechsel — von vorn lesen.
        start = 0

    if start >= size:
        return ("", inode, size)

    chunk_bytes = min(MAX_BYTES_PER_RUN, size - start)
    # `tail -c +N` ist 1-basiert: byte N ist das erste zurueckgegebene.
    cmd = f"tail -c +{start + 1} {log_path!s} | head -c {chunk_bytes}"
    out = ssh_runner.run_on_host(host, cmd, timeout=30)
    if out.exit_code != 0:
        raise RuntimeError(f"tail failed: {out.stderr.strip() or out.exit_code}")
    # Letzte Zeile koennte unvollstaendig sein. Wir kuerzen am letzten Newline
    # und verschieben den Offset entsprechend, damit der Rest beim naechsten
    # Lauf erneut gelesen wird.
    content = out.stdout
    last_nl = content.rfind("\n")
    if last_nl == -1:
        # Eine einzige, lange Zeile ohne Newline — entweder zu klein zum
        # Anwenden oder Caddy hat noch nicht geflusht. Wir verschlucken.
        return ("", inode, start)
    consumed = last_nl + 1
    return (content[:consumed], inode, start + consumed)


def _upsert_sample(
    session: Session,
    *,
    bucket_ts: str,
    host_id: str,
    server_name: str,
    app_id: str | None,
    agg: dict,
) -> None:
    """Increment-Upsert: existiert ein Bucket schon, dann addieren wir.

    Latenzen koennen wir nicht stabil "addieren" — wir nehmen den
    schlechteren Wert (max) und mitteln p50/p95 grob. Bei 1-Minuten-Buckets
    und 1-pro-Minute-Collect-Intervall sollte i.d.R. nur ein Insert pro
    Bucket noetig sein; Mehrfach-Aggregation tritt nur auf, wenn der
    Collector wegen Rotation/Recovery noch mal alte Zeit nachholt.
    """
    p50, p95, mx = caddy_log.percentiles(agg["latencies"])
    existing = (
        session.query(TrafficSampleRow)
        .filter(TrafficSampleRow.bucket_ts == bucket_ts)
        .filter(TrafficSampleRow.bucket_size == "1m")
        .filter(TrafficSampleRow.host_id == host_id)
        .filter(TrafficSampleRow.server_name == server_name)
        .filter(TrafficSampleRow.app_id == app_id)
        .one_or_none()
    )
    if existing is None:
        row = TrafficSampleRow(
            id=str(uuid.uuid4()),
            bucket_ts=bucket_ts,
            bucket_size="1m",
            host_id=host_id,
            server_name=server_name,
            app_id=app_id,
            requests=agg["requests"],
            status_2xx=agg["status_2xx"],
            status_3xx=agg["status_3xx"],
            status_4xx=agg["status_4xx"],
            status_5xx=agg["status_5xx"],
            bytes_out=agg["bytes_out"],
            latency_p50_ms=p50,
            latency_p95_ms=p95,
            latency_max_ms=mx,
            created_at=_now_iso(),
        )
        session.add(row)
        return

    # Inkrement
    existing.requests = (existing.requests or 0) + agg["requests"]
    existing.status_2xx = (existing.status_2xx or 0) + agg["status_2xx"]
    existing.status_3xx = (existing.status_3xx or 0) + agg["status_3xx"]
    existing.status_4xx = (existing.status_4xx or 0) + agg["status_4xx"]
    existing.status_5xx = (existing.status_5xx or 0) + agg["status_5xx"]
    existing.bytes_out = (existing.bytes_out or 0) + agg["bytes_out"]
    if mx is not None:
        existing.latency_max_ms = max(existing.latency_max_ms or 0, mx)
    if p95 is not None:
        # Konservativ: max(alt, neu) — overstates leicht, ist aber stabil.
        existing.latency_p95_ms = max(existing.latency_p95_ms or 0, p95)
    if p50 is not None:
        existing.latency_p50_ms = max(existing.latency_p50_ms or 0, p50)


def _collect_source(session: Session, source: TrafficSourceRow) -> dict:
    """Verarbeitet eine einzelne Traffic-Quelle. Gibt Status-Dict zurueck."""
    host = session.get(HostRow, source.host_id)
    if host is None:
        return {"ok": False, "error": "host_missing"}

    try:
        content, inode, new_offset = _ssh_tail(host, source.log_path, source.last_offset or 0)
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": f"tail: {exc}"}

    # Rotation: anderes Inode → wir haben gerade NEU gelesen ab 0. last_inode
    # nur dann ueberschreiben wenn wirklich etwas drinsteht (sonst beim
    # erstmaligen Lesen kein Reset-Signal verlieren).
    if source.last_inode and source.last_inode != inode:
        log.info("Caddy-Log-Rotation auf %s (inode %s -> %s)", host.name, source.last_inode, inode)

    if not content:
        source.last_offset = new_offset
        source.last_inode = inode
        source.last_collect_at = _now_iso()
        source.last_status = "ok"
        source.last_error = None
        source.updated_at = _now_iso()
        return {"ok": True, "lines": 0}

    # Parse + aggregate
    lines = content.splitlines()
    entries = list(caddy_log.parse_lines(iter(lines)))
    buckets = caddy_log.aggregate(iter(entries))

    # Server→App-Mapping aufloesen
    server_app_map = []
    try:
        server_app_map = json.loads(source.server_app_map or "[]")
    except (ValueError, TypeError):
        server_app_map = []
    app_name_to_id: dict[str, str] = {}
    if server_app_map:
        for a in session.query(AppRow).filter(AppRow.host_id == host.id).all():
            app_name_to_id[a.name] = a.id

    for (bucket_ts, server_name), agg in buckets.items():
        app_id = caddy_log.resolve_app_id(server_name, server_app_map, app_name_to_id)
        _upsert_sample(
            session,
            bucket_ts=bucket_ts,
            host_id=host.id,
            server_name=server_name,
            app_id=app_id,
            agg=agg,
        )

    source.last_offset = new_offset
    source.last_inode = inode
    source.last_collect_at = _now_iso()
    source.last_status = "ok"
    source.last_error = None
    source.updated_at = _now_iso()
    return {"ok": True, "lines": len(entries), "buckets": len(buckets)}


def collect_once() -> dict:
    """Geht einmal alle aktivierten Quellen durch."""
    factory = get_session_factory()
    summary = {"sources": 0, "ok": 0, "failed": 0, "lines": 0}
    with factory() as session:
        sources = (
            session.query(TrafficSourceRow)
            .filter(TrafficSourceRow.enabled == 1)
            .all()
        )
        summary["sources"] = len(sources)
        for src in sources:
            try:
                res = _collect_source(session, src)
            except Exception as exc:  # noqa: BLE001
                log.exception("Traffic-Collect %s: %s", src.id, exc)
                src.last_status = "failed"
                src.last_error = str(exc)[:500]
                src.updated_at = _now_iso()
                summary["failed"] += 1
                continue
            if res.get("ok"):
                summary["ok"] += 1
                summary["lines"] += int(res.get("lines") or 0)
            else:
                src.last_status = "failed"
                src.last_error = res.get("error", "unknown")
                src.updated_at = _now_iso()
                summary["failed"] += 1
        session.commit()
    return summary


async def traffic_loop(stop_event: asyncio.Event, *, interval_s: int = 60) -> None:
    log.info("Traffic-Collector startet (interval=%ds).", interval_s)
    while not stop_event.is_set():
        try:
            res = await asyncio.to_thread(collect_once)
            if res.get("sources"):
                log.info(
                    "Traffic-Collect: sources=%d ok=%d failed=%d lines=%d",
                    res["sources"], res["ok"], res["failed"], res["lines"],
                )
        except Exception as exc:  # noqa: BLE001
            log.warning("Traffic-Loop: %s", exc)
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=interval_s)
        except TimeoutError:
            continue
    log.info("Traffic-Collector stoppt.")
