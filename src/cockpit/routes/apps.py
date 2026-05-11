"""Apps-Routes."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from sqlalchemy.orm import Session

from ..auth import client_ip, require_auth
from ..crud import apps as crud_apps
from ..crud import hosts as crud_hosts
from ..db import get_session
from ..models import (
    AppCreate,
    AppDetail,
    AppOut,
    AppUpdate,
    ContainerInfo,
    app_row_to_out,
)
from ..services import docker_inspect, health_check

router = APIRouter(prefix="/admin/api/apps", tags=["apps"])


def _host_index(session: Session) -> dict[str, str]:
    return {h.id: h.name for h in crud_hosts.list_hosts(session)}


@router.get("", response_model=list[AppOut])
async def list_apps(_=Depends(require_auth), session: Session = Depends(get_session)) -> list[AppOut]:
    rows = crud_apps.list_apps(session)
    idx = _host_index(session)
    return [app_row_to_out(r, host_name=idx.get(r.host_id, "?")) for r in rows]


@router.post("", response_model=AppOut, status_code=201)
async def create_app(
    payload: AppCreate,
    request: Request,
    _=Depends(require_auth),
    session: Session = Depends(get_session),
) -> AppOut:
    try:
        row = crud_apps.create_app(session, payload, ip=client_ip(request))
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    idx = _host_index(session)
    return app_row_to_out(row, host_name=idx.get(row.host_id, "?"))


@router.get("/{app_id}", response_model=AppDetail)
async def get_app_detail(app_id: str, _=Depends(require_auth), session: Session = Depends(get_session)) -> AppDetail:
    row = crud_apps.get_app(session, app_id)
    if row is None:
        raise HTTPException(status_code=404, detail="App not found")
    host = crud_hosts.get_host(session, row.host_id)
    if host is None:
        raise HTTPException(status_code=404, detail="Host not found")
    summary = docker_inspect.summarize_app(host, filter_expr=row.container_filter or f"name={row.name}")
    out = app_row_to_out(row, host_name=host.name, summary=summary)
    return AppDetail(
        **out.model_dump(),
        containers=[ContainerInfo(**c) for c in summary["containers"]],
        health_http=None,
    )


@router.patch("/{app_id}", response_model=AppOut)
async def update_app(
    app_id: str,
    patch: AppUpdate,
    request: Request,
    _=Depends(require_auth),
    session: Session = Depends(get_session),
) -> AppOut:
    try:
        row = crud_apps.update_app(session, app_id, patch, ip=client_ip(request))
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if row is None:
        raise HTTPException(status_code=404, detail="App not found")
    idx = _host_index(session)
    return app_row_to_out(row, host_name=idx.get(row.host_id, "?"))


@router.delete("/{app_id}", status_code=204)
async def delete_app(
    app_id: str,
    request: Request,
    _=Depends(require_auth),
    session: Session = Depends(get_session),
) -> Response:
    ok = crud_apps.delete_app(session, app_id, ip=client_ip(request))
    if not ok:
        raise HTTPException(status_code=404, detail="App not found")
    return Response(status_code=204)


@router.post("/{app_id}/health-check", response_model=AppOut)
async def app_health_check(
    app_id: str,
    _=Depends(require_auth),
    session: Session = Depends(get_session),
) -> AppOut:
    row = crud_apps.get_app(session, app_id)
    if row is None:
        raise HTTPException(status_code=404, detail="App not found")
    host = crud_hosts.get_host(session, row.host_id)
    if host is None:
        raise HTTPException(status_code=404, detail="Host not found")
    health_check.check_app(session, row, host)
    row = crud_apps.get_app(session, app_id)
    return app_row_to_out(row, host_name=host.name)


@router.post("/{app_id}/restart")
async def app_restart(
    app_id: str,
    request: Request,
    _=Depends(require_auth),
    session: Session = Depends(get_session),
) -> dict:
    row = crud_apps.get_app(session, app_id)
    if row is None:
        raise HTTPException(status_code=404, detail="App not found")
    host = crud_hosts.get_host(session, row.host_id)
    if host is None:
        raise HTTPException(status_code=404, detail="Host not found")
    from ..crud import audit
    result = docker_inspect.restart_app(host, compose_path=row.compose_path, container_filter=row.container_filter)
    audit.write(
        session,
        action="app.restart",
        target=app_id,
        after={"name": row.name, "host": host.name, "ok": result["ok"]},
        ip=client_ip(request),
        notes=result.get("error") or "",
    )
    return result


@router.get("/{app_id}/logs")
async def app_logs(
    app_id: str,
    tail: int = Query(200, ge=1, le=5000),
    _=Depends(require_auth),
    session: Session = Depends(get_session),
) -> dict:
    row = crud_apps.get_app(session, app_id)
    if row is None:
        raise HTTPException(status_code=404, detail="App not found")
    host = crud_hosts.get_host(session, row.host_id)
    if host is None:
        raise HTTPException(status_code=404, detail="Host not found")
    text = docker_inspect.fetch_logs(
        host, compose_path=row.compose_path, container_filter=row.container_filter, tail=tail,
    )
    return {"app_id": app_id, "tail": tail, "logs": text}
