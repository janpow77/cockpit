"""Auth-Endpoints: Login, Logout, Me."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.orm import Session

from ..auth import (
    cleanup_expired,
    client_ip,
    issue_token,
    require_auth,
    revoke_token,
    verify_password,
)
from ..config import load_config
from ..db import get_session
from ..models import LoginRequest, LoginResponse, MeResponse

router = APIRouter(prefix="/admin/api/auth", tags=["auth"])


@router.post("/login", response_model=LoginResponse)
async def login(
    req: LoginRequest, request: Request, response: Response, session: Session = Depends(get_session)
) -> LoginResponse:
    benutzer = (req.username or "admin").strip()
    if benutzer != load_config().admin_user or not verify_password(req.password):
        raise HTTPException(status_code=401, detail="Benutzername oder Passwort falsch")
    cleanup_expired(session)
    token, expires = issue_token(session, ip=client_ip(request))
    response.headers["Cache-Control"] = "no-store"
    return LoginResponse(token=token, expires_at=expires)


@router.post("/logout", status_code=204)
async def logout(session_row=Depends(require_auth), session: Session = Depends(get_session)) -> Response:
    revoke_token(session, session_row.token)
    return Response(status_code=204, headers={"Cache-Control": "no-store"})


@router.get("/me", response_model=MeResponse)
async def me(session_row=Depends(require_auth)) -> MeResponse:
    from ..auth import _from_iso

    try:
        expires = _from_iso(session_row.expires_at)
    except ValueError:
        expires = None
    return MeResponse(logged_in=True, expires_at=expires)
