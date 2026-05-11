"""CRUD fuer Traffic-Quellen und Sample-Series-Reads."""
from __future__ import annotations

import json
import secrets
import time
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from ..models import (
    AppRow,
    TrafficSampleRow,
    TrafficSourceCreate,
    TrafficSourceRow,
    TrafficSourceUpdate,
)
from . import audit


def _new_id() -> str:
    return f"ts_{int(time.time() * 1000):x}_{secrets.token_hex(3)}"


def _iso_now() -> str:
    return datetime.now(tz=UTC).isoformat().replace("+00:00", "Z")


def list_sources(session: Session) -> list[TrafficSourceRow]:
    return session.query(TrafficSourceRow).order_by(TrafficSourceRow.created_at).all()


def get_source(session: Session, source_id: str) -> TrafficSourceRow | None:
    return session.get(TrafficSourceRow, source_id)


def create_source(
    session: Session,
    payload: TrafficSourceCreate,
    *,
    ip: str | None = None,
) -> TrafficSourceRow:
    existing = (
        session.query(TrafficSourceRow)
        .filter(TrafficSourceRow.host_id == payload.host_id)
        .filter(TrafficSourceRow.log_path == payload.log_path)
        .one_or_none()
    )
    if existing is not None:
        raise ValueError("Traffic-Source mit dieser host/log_path-Kombi existiert bereits.")

    row = TrafficSourceRow(
        id=_new_id(),
        host_id=payload.host_id,
        log_path=payload.log_path,
        log_format=payload.log_format,
        server_app_map=json.dumps(payload.server_app_map or []),
        enabled=1 if payload.enabled else 0,
        last_offset=0,
        last_status="never",
        created_at=_iso_now(),
        updated_at=_iso_now(),
    )
    session.add(row)
    session.flush()
    audit.write(
        session,
        action="traffic.source.create",
        target=row.id,
        after={"host_id": row.host_id, "log_path": row.log_path},
        ip=ip,
        commit=False,
    )
    session.commit()
    return row


def update_source(
    session: Session,
    source_id: str,
    patch: TrafficSourceUpdate,
    *,
    ip: str | None = None,
) -> TrafficSourceRow | None:
    row = session.get(TrafficSourceRow, source_id)
    if row is None:
        return None
    before = {
        "log_path": row.log_path,
        "log_format": row.log_format,
        "server_app_map": row.server_app_map,
        "enabled": bool(row.enabled),
    }
    if patch.log_path is not None:
        row.log_path = patch.log_path
    if patch.log_format is not None:
        row.log_format = patch.log_format
    if patch.server_app_map is not None:
        row.server_app_map = json.dumps(patch.server_app_map)
    if patch.enabled is not None:
        row.enabled = 1 if patch.enabled else 0
    row.updated_at = _iso_now()
    session.flush()
    audit.write(
        session,
        action="traffic.source.update",
        target=row.id,
        before=before,
        after={"log_path": row.log_path, "enabled": bool(row.enabled)},
        ip=ip,
        commit=False,
    )
    session.commit()
    return row


def delete_source(session: Session, source_id: str, *, ip: str | None = None) -> bool:
    row = session.get(TrafficSourceRow, source_id)
    if row is None:
        return False
    audit.write(
        session,
        action="traffic.source.delete",
        target=source_id,
        before={"log_path": row.log_path, "host_id": row.host_id},
        ip=ip,
        commit=False,
    )
    session.delete(row)
    session.commit()
    return True


# ---------------------------- Series-Reads --------------------------------


_BUCKET_SECONDS = {
    "1m": 60,
    "5m": 300,
    "1h": 3600,
    "1d": 86400,
}


def _bucket_format(bucket_size: str) -> str:
    """SQLite ``strftime``-Pattern fuer Roll-up auf groessere Buckets.

    Quell-Buckets in ``cockpit_traffic_samples`` sind 1m; fuer 5m/1h/1d
    aggregieren wir on-the-fly via GROUP BY auf den gerundeten Timestamp.
    """
    if bucket_size == "5m":
        # Auf 5 Minuten runden: strftime + integer-div * 5
        return "strftime('%Y-%m-%dT%H:', bucket_ts) || printf('%02d:00Z', (CAST(strftime('%M', bucket_ts) AS INTEGER) / 5) * 5)"
    if bucket_size == "1h":
        return "strftime('%Y-%m-%dT%H:00:00Z', bucket_ts)"
    if bucket_size == "1d":
        return "strftime('%Y-%m-%dT00:00:00Z', bucket_ts)"
    return "bucket_ts"  # 1m


def series(
    session: Session,
    *,
    app_id: str | None,
    host_id: str | None,
    server_name: str | None,
    bucket_size: str,
    from_ts: datetime,
    to_ts: datetime,
) -> list[dict]:
    """Liefert aggregierte Series-Punkte fuer den angefragten Zeitraum."""
    if bucket_size not in _BUCKET_SECONDS:
        raise ValueError(f"Unbekannte bucket_size: {bucket_size}")
    from_iso = from_ts.isoformat().replace("+00:00", "Z")
    to_iso = to_ts.isoformat().replace("+00:00", "Z")
    bucket_expr = _bucket_format(bucket_size)

    # Wir aggregieren immer aus den 1m-Quell-Samples — Roll-up zur Lesezeit.
    from sqlalchemy import text as _t
    where_parts = [
        "bucket_size = '1m'",
        "bucket_ts >= :from_ts",
        "bucket_ts < :to_ts",
    ]
    params: dict = {"from_ts": from_iso, "to_ts": to_iso}
    if app_id is not None:
        where_parts.append("app_id = :app_id")
        params["app_id"] = app_id
    if host_id is not None:
        where_parts.append("host_id = :host_id")
        params["host_id"] = host_id
    if server_name is not None:
        where_parts.append("server_name = :server_name")
        params["server_name"] = server_name.lower()

    sql = f"""
        SELECT
            {bucket_expr} AS bucket_ts,
            SUM(requests) AS requests,
            SUM(status_2xx) AS status_2xx,
            SUM(status_3xx) AS status_3xx,
            SUM(status_4xx) AS status_4xx,
            SUM(status_5xx) AS status_5xx,
            SUM(bytes_out) AS bytes_out,
            MAX(latency_p50_ms) AS latency_p50_ms,
            MAX(latency_p95_ms) AS latency_p95_ms,
            MAX(latency_max_ms) AS latency_max_ms
        FROM cockpit_traffic_samples
        WHERE {' AND '.join(where_parts)}
        GROUP BY 1
        ORDER BY 1 ASC
        LIMIT 10000
    """
    rows = session.execute(_t(sql), params).all()
    return [
        {
            "bucket_ts": r.bucket_ts,
            "requests": int(r.requests or 0),
            "status_2xx": int(r.status_2xx or 0),
            "status_3xx": int(r.status_3xx or 0),
            "status_4xx": int(r.status_4xx or 0),
            "status_5xx": int(r.status_5xx or 0),
            "bytes_out": int(r.bytes_out or 0),
            "latency_p50_ms": int(r.latency_p50_ms) if r.latency_p50_ms is not None else None,
            "latency_p95_ms": int(r.latency_p95_ms) if r.latency_p95_ms is not None else None,
            "latency_max_ms": int(r.latency_max_ms) if r.latency_max_ms is not None else None,
        }
        for r in rows
    ]


def purge_older_than(session: Session, *, days: int) -> int:
    """Loescht Traffic-Samples aelter als N Tage. Retention-Policy."""
    cutoff = (datetime.now(tz=UTC) - timedelta(days=days)).isoformat().replace("+00:00", "Z")
    n = (
        session.query(TrafficSampleRow)
        .filter(TrafficSampleRow.bucket_ts < cutoff)
        .delete(synchronize_session=False)
    )
    session.commit()
    return int(n)
