"""Backups-CRUD."""
from __future__ import annotations

import secrets
import time
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from ..models import BackupCreate, BackupRow, BackupUpdate, HostRow
from . import audit


def _new_id() -> str:
    return f"b_{int(time.time() * 1000):x}_{secrets.token_hex(3)}"


def _iso_now() -> str:
    return datetime.now(tz=UTC).isoformat().replace("+00:00", "Z")


def list_backups(session: Session) -> list[BackupRow]:
    return session.query(BackupRow).order_by(BackupRow.name.asc()).all()


def get_backup(session: Session, backup_id: str) -> BackupRow | None:
    return session.get(BackupRow, backup_id)


def host_name_for(session: Session, host_id: str) -> str:
    h = session.get(HostRow, host_id)
    return h.name if h else "?"


def create_backup(session: Session, payload: BackupCreate, *, ip: str | None = None) -> BackupRow:
    host = session.get(HostRow, payload.host_id)
    if host is None:
        raise ValueError(f"Host '{payload.host_id}' existiert nicht")
    existing = session.query(BackupRow).filter(BackupRow.name == payload.name).one_or_none()
    if existing:
        raise ValueError(f"Backup '{payload.name}' existiert bereits")
    now = _iso_now()
    row = BackupRow(
        id=_new_id(),
        name=payload.name,
        host_id=payload.host_id,
        backup_type=payload.backup_type,
        command=payload.command,
        target_path=payload.target_path,
        schedule_cron=payload.schedule_cron,
        enabled=int(payload.enabled),
        last_run_status="never",
        created_at=now,
        updated_at=now,
    )
    session.add(row)
    session.commit()
    audit.write(session, action="backup.create", target=row.id, after={
        "name": row.name, "host": host.name, "type": row.backup_type,
    }, ip=ip)
    return row


def update_backup(session: Session, backup_id: str, patch: BackupUpdate, *, ip: str | None = None) -> BackupRow | None:
    row = get_backup(session, backup_id)
    if row is None:
        return None
    before = {
        "name": row.name, "command": row.command, "target_path": row.target_path,
        "enabled": bool(row.enabled),
    }
    if patch.name is not None and patch.name != row.name:
        existing = session.query(BackupRow).filter(BackupRow.name == patch.name, BackupRow.id != row.id).one_or_none()
        if existing:
            raise ValueError(f"Backup '{patch.name}' existiert bereits")
        row.name = patch.name
    if patch.backup_type is not None:
        row.backup_type = patch.backup_type
    if patch.command is not None:
        row.command = patch.command
    if patch.target_path is not None:
        row.target_path = patch.target_path
    if patch.schedule_cron is not None:
        row.schedule_cron = patch.schedule_cron
    if patch.enabled is not None:
        row.enabled = int(patch.enabled)
    row.updated_at = _iso_now()
    session.commit()
    audit.write(session, action="backup.update", target=row.id, before=before, after={
        "name": row.name, "enabled": bool(row.enabled),
    }, ip=ip)
    return row


def delete_backup(session: Session, backup_id: str, *, ip: str | None = None) -> bool:
    row = get_backup(session, backup_id)
    if row is None:
        return False
    name = row.name
    session.delete(row)
    session.commit()
    audit.write(session, action="backup.delete", target=backup_id, before={"name": name}, ip=ip)
    return True


def record_run(
    session: Session,
    backup_id: str,
    *,
    status: str,
    log_excerpt: str = "",
    bytes_total: int | None = None,
) -> BackupRow | None:
    row = get_backup(session, backup_id)
    if row is None:
        return None
    row.last_run_at = _iso_now()
    row.last_run_status = status
    row.last_run_log = log_excerpt[-4000:] if log_excerpt else None
    if bytes_total is not None:
        row.last_size_bytes = bytes_total
    row.updated_at = _iso_now()
    session.commit()
    return row
