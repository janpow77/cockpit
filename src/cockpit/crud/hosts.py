"""Hosts-CRUD."""
from __future__ import annotations

import secrets
import time
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from ..models import HostCreate, HostRow, HostUpdate
from . import audit


def _new_id() -> str:
    return f"h_{int(time.time() * 1000):x}_{secrets.token_hex(3)}"


def _iso_now() -> str:
    return datetime.now(tz=UTC).isoformat().replace("+00:00", "Z")


def list_hosts(session: Session) -> list[HostRow]:
    return session.query(HostRow).order_by(HostRow.is_self.desc(), HostRow.name.asc()).all()


def get_host(session: Session, host_id: str) -> HostRow | None:
    return session.get(HostRow, host_id)


def get_host_by_name(session: Session, name: str) -> HostRow | None:
    return session.query(HostRow).filter(HostRow.name == name).one_or_none()


def create_host(session: Session, payload: HostCreate, *, ip: str | None = None) -> HostRow:
    if get_host_by_name(session, payload.name):
        raise ValueError(f"Host '{payload.name}' existiert bereits")
    now = _iso_now()
    row = HostRow(
        id=_new_id(),
        name=payload.name,
        tailscale_ip=payload.tailscale_ip,
        description=payload.description,
        ssh_user=payload.ssh_user,
        ssh_key_path=payload.ssh_key_path,
        is_self=int(payload.is_self),
        enabled=int(payload.enabled),
        last_status="unknown",
        created_at=now,
        updated_at=now,
    )
    session.add(row)
    session.commit()
    audit.write(
        session,
        action="host.create",
        target=row.id,
        after={"name": row.name, "tailscale_ip": row.tailscale_ip},
        ip=ip,
    )
    return row


def update_host(session: Session, host_id: str, patch: HostUpdate, *, ip: str | None = None) -> HostRow | None:
    row = get_host(session, host_id)
    if row is None:
        return None
    before = {
        "name": row.name,
        "tailscale_ip": row.tailscale_ip,
        "description": row.description,
        "ssh_user": row.ssh_user,
        "is_self": bool(row.is_self),
        "enabled": bool(row.enabled),
    }
    if patch.name is not None and patch.name != row.name:
        existing = get_host_by_name(session, patch.name)
        if existing and existing.id != row.id:
            raise ValueError(f"Host '{patch.name}' existiert bereits")
        row.name = patch.name
    if patch.tailscale_ip is not None:
        row.tailscale_ip = patch.tailscale_ip
    if patch.description is not None:
        row.description = patch.description
    if patch.ssh_user is not None:
        row.ssh_user = patch.ssh_user
    if patch.ssh_key_path is not None:
        row.ssh_key_path = patch.ssh_key_path
    if patch.is_self is not None:
        row.is_self = int(patch.is_self)
    if patch.enabled is not None:
        row.enabled = int(patch.enabled)
    row.updated_at = _iso_now()
    session.commit()
    audit.write(session, action="host.update", target=row.id, before=before, after={
        "name": row.name, "tailscale_ip": row.tailscale_ip, "enabled": bool(row.enabled),
    }, ip=ip)
    return row


def delete_host(session: Session, host_id: str, *, ip: str | None = None) -> bool:
    row = get_host(session, host_id)
    if row is None:
        return False
    name = row.name
    session.delete(row)
    session.commit()
    audit.write(session, action="host.delete", target=host_id, before={"name": name}, ip=ip)
    return True


def update_status(
    session: Session,
    host_id: str,
    *,
    status: str,
    error: str | None = None,
) -> HostRow | None:
    row = get_host(session, host_id)
    if row is None:
        return None
    row.last_status = status
    row.last_error = error
    row.last_check_at = _iso_now()
    row.updated_at = _iso_now()
    session.commit()
    return row
