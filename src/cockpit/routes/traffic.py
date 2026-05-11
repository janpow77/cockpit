"""Traffic-Routes: Caddy-Log-Quellen + Series-Reads."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from sqlalchemy.orm import Session

from ..auth import client_ip, require_auth
from ..crud import hosts as crud_hosts
from ..crud import traffic as crud_traffic
from ..db import get_session
from ..models import (
    TrafficBucketSize,
    TrafficPoint,
    TrafficSeriesResponse,
    TrafficSourceCreate,
    TrafficSourceOut,
    TrafficSourceUpdate,
    traffic_source_row_to_out,
)
from ..services import traffic_collector

router = APIRouter(prefix="/admin/api/traffic", tags=["traffic"])


def _host_index(session: Session) -> dict[str, str]:
    return {h.id: h.name for h in crud_hosts.list_hosts(session)}


@router.get("/sources", response_model=list[TrafficSourceOut])
async def list_sources(
    _=Depends(require_auth),
    session: Session = Depends(get_session),
) -> list[TrafficSourceOut]:
    rows = crud_traffic.list_sources(session)
    idx = _host_index(session)
    return [traffic_source_row_to_out(r, host_name=idx.get(r.host_id, "?")) for r in rows]


@router.post("/sources", response_model=TrafficSourceOut, status_code=201)
async def create_source(
    payload: TrafficSourceCreate,
    request: Request,
    _=Depends(require_auth),
    session: Session = Depends(get_session),
) -> TrafficSourceOut:
    if crud_hosts.get_host(session, payload.host_id) is None:
        raise HTTPException(status_code=404, detail="Host not found")
    try:
        row = crud_traffic.create_source(session, payload, ip=client_ip(request))
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    idx = _host_index(session)
    return traffic_source_row_to_out(row, host_name=idx.get(row.host_id, "?"))


@router.patch("/sources/{source_id}", response_model=TrafficSourceOut)
async def update_source(
    source_id: str,
    patch: TrafficSourceUpdate,
    request: Request,
    _=Depends(require_auth),
    session: Session = Depends(get_session),
) -> TrafficSourceOut:
    row = crud_traffic.update_source(session, source_id, patch, ip=client_ip(request))
    if row is None:
        raise HTTPException(status_code=404, detail="Traffic-Source not found")
    idx = _host_index(session)
    return traffic_source_row_to_out(row, host_name=idx.get(row.host_id, "?"))


@router.delete("/sources/{source_id}", status_code=204)
async def delete_source(
    source_id: str,
    request: Request,
    _=Depends(require_auth),
    session: Session = Depends(get_session),
) -> Response:
    ok = crud_traffic.delete_source(session, source_id, ip=client_ip(request))
    if not ok:
        raise HTTPException(status_code=404, detail="Traffic-Source not found")
    return Response(status_code=204)


@router.post("/collect")
async def collect_now(_=Depends(require_auth)) -> dict:
    """Triggert einen Sammellauf manuell. Antwort enthaelt die Lauf-Summary."""
    return traffic_collector.collect_once()


@router.get("/series", response_model=TrafficSeriesResponse)
async def series(
    app_id: str | None = Query(default=None),
    host_id: str | None = Query(default=None),
    server_name: str | None = Query(default=None),
    bucket: TrafficBucketSize = Query(default="5m"),
    window: str = Query(
        default="6h",
        pattern=r"^\d+[mhd]$",
        description="Zeitraum-Suffix: 30m / 6h / 7d. Maximum 30d.",
    ),
    _=Depends(require_auth),
    session: Session = Depends(get_session),
) -> TrafficSeriesResponse:
    # Window-String parsen
    unit = window[-1]
    amount = int(window[:-1])
    if unit == "m":
        delta = timedelta(minutes=amount)
    elif unit == "h":
        delta = timedelta(hours=amount)
    elif unit == "d":
        delta = timedelta(days=amount)
    else:
        raise HTTPException(status_code=400, detail="Ungueltiges window-Format")
    if delta > timedelta(days=30):
        raise HTTPException(status_code=400, detail="window > 30d nicht erlaubt")

    to_ts = datetime.now(tz=UTC).replace(second=0, microsecond=0)
    from_ts = to_ts - delta

    try:
        rows = crud_traffic.series(
            session,
            app_id=app_id,
            host_id=host_id,
            server_name=server_name,
            bucket_size=bucket,
            from_ts=from_ts,
            to_ts=to_ts,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    points = [TrafficPoint(**r) for r in rows]
    total_requests = sum(p.requests for p in points)
    total_errors = sum(p.status_4xx + p.status_5xx for p in points)
    error_rate = (total_errors / total_requests) if total_requests else 0.0

    return TrafficSeriesResponse(
        bucket_size=bucket,
        app_id=app_id,
        host_id=host_id,
        from_ts=from_ts,
        to_ts=to_ts,
        total_requests=total_requests,
        error_rate=round(error_rate, 4),
        points=points,
    )


@router.post("/purge")
async def purge_old_samples(
    request: Request,
    days: int = Query(default=90, ge=7, le=730),
    _=Depends(require_auth),
    session: Session = Depends(get_session),
) -> dict:
    deleted = crud_traffic.purge_older_than(session, days=days)
    from ..crud import audit
    audit.write(
        session,
        action="traffic.purge",
        after={"days": days, "deleted": deleted},
        ip=client_ip(request),
    )
    return {"deleted": deleted, "older_than_days": days}
