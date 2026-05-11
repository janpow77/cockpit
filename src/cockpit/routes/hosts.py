"""Hosts-Routes."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.orm import Session

from ..auth import client_ip, require_auth
from ..crud import hosts as crud_hosts
from ..db import get_session
from ..models import HostCreate, HostOut, HostUpdate, host_row_to_out
from ..services import health_check, tailscale

router = APIRouter(prefix="/admin/api/hosts", tags=["hosts"])


@router.get("", response_model=list[HostOut])
async def list_hosts(_=Depends(require_auth), session: Session = Depends(get_session)) -> list[HostOut]:
    rows = crud_hosts.list_hosts(session)
    return [host_row_to_out(r) for r in rows]


@router.post("", response_model=HostOut, status_code=201)
async def create_host(
    payload: HostCreate,
    request: Request,
    _=Depends(require_auth),
    session: Session = Depends(get_session),
) -> HostOut:
    try:
        row = crud_hosts.create_host(session, payload, ip=client_ip(request))
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return host_row_to_out(row)


@router.get("/tailscale-status")
async def tailscale_status(_=Depends(require_auth)) -> dict:
    raw = tailscale.status()
    return {
        "ok": "error" not in raw,
        "raw": raw,
        "by_ip": tailscale.peer_status_by_ip(),
    }


@router.get("/{host_id}", response_model=HostOut)
async def get_host(host_id: str, _=Depends(require_auth), session: Session = Depends(get_session)) -> HostOut:
    row = crud_hosts.get_host(session, host_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Host not found")
    return host_row_to_out(row)


@router.patch("/{host_id}", response_model=HostOut)
async def update_host(
    host_id: str,
    patch: HostUpdate,
    request: Request,
    _=Depends(require_auth),
    session: Session = Depends(get_session),
) -> HostOut:
    try:
        row = crud_hosts.update_host(session, host_id, patch, ip=client_ip(request))
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if row is None:
        raise HTTPException(status_code=404, detail="Host not found")
    return host_row_to_out(row)


@router.delete("/{host_id}", status_code=204)
async def delete_host(
    host_id: str,
    request: Request,
    _=Depends(require_auth),
    session: Session = Depends(get_session),
) -> Response:
    ok = crud_hosts.delete_host(session, host_id, ip=client_ip(request))
    if not ok:
        raise HTTPException(status_code=404, detail="Host not found")
    return Response(status_code=204)


@router.get("/{host_id}/health")
async def host_health(host_id: str, _=Depends(require_auth), session: Session = Depends(get_session)) -> dict:
    row = crud_hosts.get_host(session, host_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Host not found")
    info = health_check.check_host(session, row)
    row = crud_hosts.get_host(session, host_id)
    return {"host": host_row_to_out(row).model_dump(mode="json"), "check": info}
