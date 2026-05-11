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
from ..db import get_session
from ..models import LoginRequest, LoginResponse, MeResponse

router = APIRouter(prefix="/admin/api/auth", tags=["auth"])


@router.post("/login", response_model=LoginResponse)
async def login(req: LoginRequest, request: Request, session: Session = Depends(get_session)) -> LoginResponse:
    if not verify_password(req.password):
        raise HTTPException(status_code=401, detail="Invalid password")
    cleanup_expired(session)
    token, expires = issue_token(session, ip=client_ip(request))
    return LoginResponse(token=token, expires_at=expires)


@router.post("/logout", status_code=204)
async def logout(request: Request, _=Depends(require_auth), session: Session = Depends(get_session)) -> Response:
    auth_header = request.headers.get("authorization") or ""
    token = ""
    if auth_header.lower().startswith("bearer "):
        token = auth_header.split(" ", 1)[1].strip()
    if token:
        revoke_token(session, token)
    return Response(status_code=204)


@router.get("/me", response_model=MeResponse)
async def me(session_row=Depends(require_auth)) -> MeResponse:
    from ..auth import _from_iso

    try:
        expires = _from_iso(session_row.expires_at)
    except ValueError:
        expires = None
    return MeResponse(logged_in=True, expires_at=expires)
