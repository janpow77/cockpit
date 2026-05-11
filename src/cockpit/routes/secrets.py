"""Secrets-Routes (Vault)."""
from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.orm import Session

from ..auth import client_ip, require_auth
from ..crud import secrets as crud_secrets
from ..db import get_session
from ..models import (
    SecretCreate,
    SecretOut,
    SecretRevealRequest,
    SecretRevealResponse,
    SecretUpdate,
    secret_row_to_out,
)
from ..services.secret_vault import VaultDecryptError, VaultDisabledError, is_enabled

router = APIRouter(prefix="/admin/api/secrets", tags=["secrets"])


def _ensure_vault() -> None:
    if not is_enabled():
        raise HTTPException(
            status_code=503,
            detail="Vault deaktiviert: COCKPIT_VAULT_KEY nicht gesetzt. "
                   "Generiere mit `python -c \"from cryptography.fernet import Fernet; "
                   "print(Fernet.generate_key().decode())\"`",
        )


@router.get("", response_model=list[SecretOut])
async def list_secrets(_=Depends(require_auth), session: Session = Depends(get_session)) -> list[SecretOut]:
    """Liste OHNE Werte. Reveal nur ueber separaten POST."""
    rows = crud_secrets.list_secrets(session)
    return [secret_row_to_out(r) for r in rows]


@router.post("", response_model=SecretOut, status_code=201)
async def create_secret(
    payload: SecretCreate,
    request: Request,
    _=Depends(require_auth),
    session: Session = Depends(get_session),
) -> SecretOut:
    _ensure_vault()
    try:
        row = crud_secrets.create_secret(session, payload, ip=client_ip(request))
    except VaultDisabledError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return secret_row_to_out(row)


@router.patch("/{secret_id}", response_model=SecretOut)
async def update_secret(
    secret_id: str,
    patch: SecretUpdate,
    request: Request,
    _=Depends(require_auth),
    session: Session = Depends(get_session),
) -> SecretOut:
    _ensure_vault()
    try:
        row = crud_secrets.update_secret(session, secret_id, patch, ip=client_ip(request))
    except VaultDisabledError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    if row is None:
        raise HTTPException(status_code=404, detail="Secret not found")
    return secret_row_to_out(row)


@router.delete("/{secret_id}", status_code=204)
async def delete_secret(
    secret_id: str,
    request: Request,
    _=Depends(require_auth),
    session: Session = Depends(get_session),
) -> Response:
    ok = crud_secrets.delete_secret(session, secret_id, ip=client_ip(request))
    if not ok:
        raise HTTPException(status_code=404, detail="Secret not found")
    return Response(status_code=204)


@router.post("/{secret_id}/reveal", response_model=SecretRevealResponse)
async def reveal_secret(
    secret_id: str,
    payload: SecretRevealRequest,
    request: Request,
    _=Depends(require_auth),
    session: Session = Depends(get_session),
) -> SecretRevealResponse:
    """Liefert den Wert einmalig im Klartext + protokolliert das Reveal mit `purpose`."""
    _ensure_vault()
    try:
        result = crud_secrets.reveal_secret(session, secret_id, purpose=payload.purpose, ip=client_ip(request))
    except VaultDisabledError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except VaultDecryptError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    if result is None:
        raise HTTPException(status_code=404, detail="Secret not found")
    row, plaintext = result
    return SecretRevealResponse(
        id=row.id,
        key=row.key,
        value=plaintext,
        revealed_at=datetime.now(tz=UTC),
        purpose=payload.purpose,
    )
