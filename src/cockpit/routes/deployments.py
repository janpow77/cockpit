"""Deployment-Historie: pro-App + global, plus Lifecycle-Hook fuer Skripte."""
from __future__ import annotations

import os

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status
from sqlalchemy.orm import Session

from ..auth import (
    _extract_token,  # noqa: F401  (intern, fuer Hook-Auth)
    client_ip,
    lookup_session,
    require_auth,
)
from ..crud import apps as crud_apps
from ..crud import deployments as crud_deployments
from ..db import get_session
from ..models import DeploymentCreate, DeploymentOut, deployment_row_to_out

router = APIRouter(prefix="/admin/api", tags=["deployments"])


def _hook_token_check(provided: str | None) -> bool:
    """Lifecycle-Hook erlaubt einen separaten Token (Env LIFECYCLE_HOOK_TOKEN).

    So muss start.sh nicht das Admin-Bearer-Token kennen, das ohnehin
    Session-rotiert wird. Token kann in /etc/auditworkshop/env oder
    /etc/audit_designer/env hinterlegt werden.
    """
    expected = os.environ.get("LIFECYCLE_HOOK_TOKEN")
    return bool(expected) and bool(provided) and provided == expected


def _auth_or_hook(
    request: Request,
    session: Session = Depends(get_session),
    x_lifecycle_token: str | None = Header(default=None, alias="X-Lifecycle-Token"),
) -> str:
    """Erlaubt EITHER Lifecycle-Hook-Token OR normales Bearer-Token.

    Gibt eine Actor-Bezeichnung zurueck: 'lifecycle-hook' oder 'admin'.
    """
    if _hook_token_check(x_lifecycle_token):
        return "lifecycle-hook"
    token = _extract_token(request)
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authorization required")
    sess = lookup_session(session, token)
    if sess is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token")
    return sess.actor or "admin"


@router.get("/apps/{app_id}/deployments", response_model=list[DeploymentOut])
async def list_app_deployments(
    app_id: str,
    limit: int = Query(default=50, ge=1, le=500),
    _=Depends(require_auth),
    session: Session = Depends(get_session),
) -> list[DeploymentOut]:
    app = crud_apps.get_app(session, app_id)
    if app is None:
        raise HTTPException(status_code=404, detail="App not found")
    rows = crud_deployments.list_for_app(session, app_id, limit=limit)
    return [deployment_row_to_out(r, app_name=app.name) for r in rows]


@router.post("/apps/{app_id}/deployments", response_model=DeploymentOut, status_code=201)
async def record_app_deployment(
    app_id: str,
    payload: DeploymentCreate,
    request: Request,
    actor: str = Depends(_auth_or_hook),
    session: Session = Depends(get_session),
) -> DeploymentOut:
    app = crud_apps.get_app(session, app_id)
    if app is None:
        raise HTTPException(status_code=404, detail="App not found")
    # Wenn Hook-Token verwendet wurde, ueberschreiben wir actor im Payload.
    if actor == "lifecycle-hook":
        payload = payload.model_copy(update={"actor": payload.actor or "lifecycle-hook"})
    try:
        row = crud_deployments.create(session, app_id, payload, ip=client_ip(request))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return deployment_row_to_out(row, app_name=app.name)


@router.get("/deployments/recent", response_model=list[DeploymentOut])
async def list_recent_deployments(
    limit: int = Query(default=50, ge=1, le=500),
    _=Depends(require_auth),
    session: Session = Depends(get_session),
) -> list[DeploymentOut]:
    rows = crud_deployments.list_recent(session, limit=limit)
    # App-Namen zur Anzeige holen
    app_names = {a.id: a.name for a in crud_apps.list_apps(session)}
    return [
        deployment_row_to_out(r, app_name=app_names.get(r.app_id, "?"))
        for r in rows
    ]


@router.get("/apps/{app_id}/deployments/current", response_model=DeploymentOut | None)
async def current_deployment(
    app_id: str,
    _=Depends(require_auth),
    session: Session = Depends(get_session),
) -> DeploymentOut | None:
    app = crud_apps.get_app(session, app_id)
    if app is None:
        raise HTTPException(status_code=404, detail="App not found")
    row = crud_deployments.current_for_app(session, app_id)
    if row is None:
        return None
    return deployment_row_to_out(row, app_name=app.name)
