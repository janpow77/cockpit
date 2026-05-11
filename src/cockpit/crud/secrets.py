"""Secrets / Vault — verschluesselt at-rest."""
from __future__ import annotations

import secrets as pysecrets
import time
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from ..models import SecretCreate, SecretRow, SecretUpdate
from ..services.secret_vault import VaultDisabledError, decrypt, encrypt
from . import audit


def _new_id() -> str:
    return f"s_{int(time.time() * 1000):x}_{pysecrets.token_hex(3)}"


def _iso_now() -> str:
    return datetime.now(tz=UTC).isoformat().replace("+00:00", "Z")


def list_secrets(session: Session) -> list[SecretRow]:
    return session.query(SecretRow).order_by(SecretRow.key.asc()).all()


def get_secret(session: Session, secret_id: str) -> SecretRow | None:
    return session.get(SecretRow, secret_id)


def get_by_key(session: Session, key: str) -> SecretRow | None:
    return session.query(SecretRow).filter(SecretRow.key == key).one_or_none()


def create_secret(session: Session, payload: SecretCreate, *, ip: str | None = None) -> SecretRow:
    """Legt einen verschluesselten Secret an. Wirft VaultDisabledError, wenn Vault aus."""
    if get_by_key(session, payload.key):
        raise ValueError(f"Secret '{payload.key}' existiert bereits")
    enc = encrypt(payload.value)  # kann VaultDisabledError werfen
    now = _iso_now()
    row = SecretRow(
        id=_new_id(),
        key=payload.key,
        value_encrypted=enc,
        app_tag=payload.app_tag,
        host_tag=payload.host_tag,
        comment=payload.comment,
        created_at=now,
        updated_at=now,
    )
    session.add(row)
    session.commit()
    audit.write(session, action="secret.create", target=row.id, after={
        "key": row.key, "app_tag": row.app_tag, "host_tag": row.host_tag,
    }, ip=ip)
    return row


def update_secret(session: Session, secret_id: str, patch: SecretUpdate, *, ip: str | None = None) -> SecretRow | None:
    row = get_secret(session, secret_id)
    if row is None:
        return None
    before = {"key": row.key, "app_tag": row.app_tag, "host_tag": row.host_tag, "comment": row.comment}
    if patch.value is not None:
        row.value_encrypted = encrypt(patch.value)
    if patch.app_tag is not None:
        row.app_tag = patch.app_tag
    if patch.host_tag is not None:
        row.host_tag = patch.host_tag
    if patch.comment is not None:
        row.comment = patch.comment
    row.updated_at = _iso_now()
    session.commit()
    audit.write(session, action="secret.update", target=row.id, before=before, after={
        "key": row.key, "app_tag": row.app_tag, "value_changed": patch.value is not None,
    }, ip=ip)
    return row


def delete_secret(session: Session, secret_id: str, *, ip: str | None = None) -> bool:
    row = get_secret(session, secret_id)
    if row is None:
        return False
    key = row.key
    session.delete(row)
    session.commit()
    audit.write(session, action="secret.delete", target=secret_id, before={"key": key}, ip=ip)
    return True


def reveal_secret(
    session: Session,
    secret_id: str,
    *,
    purpose: str,
    ip: str | None = None,
) -> tuple[SecretRow, str] | None:
    """Entschluesselt den Wert, fuehrt Audit-Log mit purpose und liefert (row, plaintext)."""
    row = get_secret(session, secret_id)
    if row is None:
        return None
    plaintext = decrypt(row.value_encrypted)  # kann VaultDisabledError werfen
    row.last_used_at = _iso_now()
    row.last_used_purpose = purpose
    row.reveal_count = (row.reveal_count or 0) + 1
    row.updated_at = _iso_now()
    session.commit()
    audit.write(
        session,
        action="secret.reveal",
        target=row.id,
        notes=purpose,
        after={"key": row.key, "reveal_count": row.reveal_count},
        ip=ip,
    )
    return row, plaintext


__all__ = [
    "list_secrets", "get_secret", "get_by_key", "create_secret",
    "update_secret", "delete_secret", "reveal_secret", "VaultDisabledError",
]
