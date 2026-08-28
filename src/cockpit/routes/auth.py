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

# Rate-Limit am Login: nach 5 Fehlversuchen je IP 60 s Sperre (im Prozess; genuegt fuer eine Instanz)
_MAX_FEHLER = 5
_SPERRE_S = 60
_fehler: dict[str, list[float]] = {}


def login_erlaubt(ip: str, jetzt: float | None = None) -> tuple[bool, int]:
    """(erlaubt, Restsekunden) – rein, testbar."""
    import time as _t

    jetzt = jetzt if jetzt is not None else _t.time()
    versuche = [t for t in _fehler.get(ip, []) if jetzt - t < _SPERRE_S]
    _fehler[ip] = versuche
    if len(versuche) >= _MAX_FEHLER:
        return False, int(_SPERRE_S - (jetzt - versuche[0])) + 1
    return True, 0


def login_fehlgeschlagen(ip: str, jetzt: float | None = None) -> None:
    import time as _t

    _fehler.setdefault(ip, []).append(jetzt if jetzt is not None else _t.time())


@router.post("/login", response_model=LoginResponse)
async def login(
    req: LoginRequest, request: Request, response: Response, session: Session = Depends(get_session)
) -> LoginResponse:
    ip = client_ip(request) or "?"
    erlaubt, rest = login_erlaubt(ip)
    if not erlaubt:
        raise HTTPException(status_code=429, detail=f"Zu viele Fehlversuche – bitte in {rest} s erneut versuchen")
    benutzer = (req.username or "admin").strip()
    if benutzer != load_config().admin_user or not verify_password(req.password):
        login_fehlgeschlagen(ip)
        raise HTTPException(status_code=401, detail="Benutzername oder Passwort falsch")
    _fehler.pop(ip, None)
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
