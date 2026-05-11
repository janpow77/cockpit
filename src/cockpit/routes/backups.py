"""Backups-Routes."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.orm import Session

from ..auth import client_ip, require_auth
from ..crud import backups as crud_backups
from ..crud import hosts as crud_hosts
from ..db import get_session
from ..models import (
    BackupCreate,
    BackupOut,
    BackupRunResult,
    BackupUpdate,
    backup_row_to_out,
)
from ..services import backup_runner

router = APIRouter(prefix="/admin/api/backups", tags=["backups"])


def _host_index(session: Session) -> dict[str, str]:
    return {h.id: h.name for h in crud_hosts.list_hosts(session)}


@router.get("", response_model=list[BackupOut])
async def list_backups(_=Depends(require_auth), session: Session = Depends(get_session)) -> list[BackupOut]:
    rows = crud_backups.list_backups(session)
    idx = _host_index(session)
    return [backup_row_to_out(r, host_name=idx.get(r.host_id, "?")) for r in rows]


@router.post("", response_model=BackupOut, status_code=201)
async def create_backup(
    payload: BackupCreate,
    request: Request,
    _=Depends(require_auth),
    session: Session = Depends(get_session),
) -> BackupOut:
    try:
        row = crud_backups.create_backup(session, payload, ip=client_ip(request))
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    idx = _host_index(session)
    return backup_row_to_out(row, host_name=idx.get(row.host_id, "?"))


@router.patch("/{backup_id}", response_model=BackupOut)
async def update_backup(
    backup_id: str,
    patch: BackupUpdate,
    request: Request,
    _=Depends(require_auth),
    session: Session = Depends(get_session),
) -> BackupOut:
    try:
        row = crud_backups.update_backup(session, backup_id, patch, ip=client_ip(request))
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if row is None:
        raise HTTPException(status_code=404, detail="Backup not found")
    idx = _host_index(session)
    return backup_row_to_out(row, host_name=idx.get(row.host_id, "?"))


@router.delete("/{backup_id}", status_code=204)
async def delete_backup(
    backup_id: str,
    request: Request,
    _=Depends(require_auth),
    session: Session = Depends(get_session),
) -> Response:
    ok = crud_backups.delete_backup(session, backup_id, ip=client_ip(request))
    if not ok:
        raise HTTPException(status_code=404, detail="Backup not found")
    return Response(status_code=204)


@router.post("/{backup_id}/run", response_model=BackupRunResult)
async def run_backup(
    backup_id: str,
    request: Request,
    _=Depends(require_auth),
    session: Session = Depends(get_session),
) -> BackupRunResult:
    row = crud_backups.get_backup(session, backup_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Backup not found")
    host = crud_hosts.get_host(session, row.host_id)
    if host is None:
        raise HTTPException(status_code=404, detail="Host not found")
    from ..crud import audit
    result = backup_runner.run_backup(session, row, host)
    audit.write(
        session,
        action="backup.run",
        target=backup_id,
        after={"name": row.name, "ok": result["ok"], "duration_ms": result["duration_ms"]},
        ip=client_ip(request),
        notes=result.get("error") or "",
    )
    return BackupRunResult(**result)


@router.post("/{backup_id}/restore-test")
async def restore_test(
    backup_id: str,
    _=Depends(require_auth),
    session: Session = Depends(get_session),
) -> dict:
    row = crud_backups.get_backup(session, backup_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Backup not found")
    # Phase 1: nur Marker — produktiver Restore-Test braucht Sandbox-Setup pro Backup-Type
    return {
        "ok": False,
        "implemented": False,
        "message": "Restore-Test ist Phase-2-Feature. Bitte manuell pruefen.",
        "target_path": row.target_path,
    }
