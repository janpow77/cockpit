"""Audit-Routes (read-only)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ..auth import require_auth
from ..crud import audit as crud_audit
from ..db import get_session
from ..models import AuditOut, audit_row_to_out

router = APIRouter(prefix="/admin/api/audit", tags=["audit"])


@router.get("", response_model=list[AuditOut])
async def list_audit(
    actor: str | None = None,
    action: str | None = None,
    target: str | None = None,
    since: str | None = None,
    limit: int = Query(200, ge=1, le=2000),
    _=Depends(require_auth),
    session: Session = Depends(get_session),
) -> list[AuditOut]:
    rows = crud_audit.list_audit(session, actor=actor, action=action, target=target, since=since, limit=limit)
    return [audit_row_to_out(r) for r in rows]
