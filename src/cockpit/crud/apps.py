"""Apps-CRUD: registrierte Container-Stacks pro Host."""
from __future__ import annotations

import json
import secrets
import time
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from ..models import AppCreate, AppRow, AppUpdate, HostRow
from . import audit


def _new_id() -> str:
    return f"app_{int(time.time() * 1000):x}_{secrets.token_hex(3)}"


def _iso_now() -> str:
    return datetime.now(tz=UTC).isoformat().replace("+00:00", "Z")


def list_apps(session: Session) -> list[AppRow]:
    return session.query(AppRow).order_by(AppRow.host_id.asc(), AppRow.name.asc()).all()


def list_apps_for_host(session: Session, host_id: str) -> list[AppRow]:
    return session.query(AppRow).filter(AppRow.host_id == host_id).order_by(AppRow.name.asc()).all()


def get_app(session: Session, app_id: str) -> AppRow | None:
    return session.get(AppRow, app_id)


def host_name_for(session: Session, host_id: str) -> str:
    h = session.get(HostRow, host_id)
    return h.name if h else "?"


def create_app(session: Session, payload: AppCreate, *, ip: str | None = None) -> AppRow:
    host = session.get(HostRow, payload.host_id)
    if host is None:
        raise ValueError(f"Host '{payload.host_id}' existiert nicht")
    existing = (
        session.query(AppRow)
        .filter(AppRow.host_id == payload.host_id, AppRow.name == payload.name)
        .one_or_none()
    )
    if existing is not None:
        raise ValueError(f"App '{payload.name}' auf Host '{host.name}' existiert bereits")
    now = _iso_now()
    row = AppRow(
        id=_new_id(),
        host_id=payload.host_id,
        name=payload.name,
        description=payload.description,
        container_filter=payload.container_filter,
        compose_path=payload.compose_path,
        healthcheck_url=payload.healthcheck_url,
        tags=json.dumps(payload.tags or []),
        enabled=int(payload.enabled),
        last_status="unknown",
        created_at=now,
        updated_at=now,
    )
    session.add(row)
    session.commit()
    audit.write(
        session,
        action="app.create",
        target=row.id,
        after={"name": row.name, "host": host.name, "filter": row.container_filter},
        ip=ip,
    )
    return row


def update_app(session: Session, app_id: str, patch: AppUpdate, *, ip: str | None = None) -> AppRow | None:
    row = get_app(session, app_id)
    if row is None:
        return None
    before = {
        "name": row.name,
        "container_filter": row.container_filter,
        "compose_path": row.compose_path,
        "healthcheck_url": row.healthcheck_url,
        "enabled": bool(row.enabled),
    }
    if patch.name is not None and patch.name != row.name:
        existing = (
            session.query(AppRow)
            .filter(AppRow.host_id == row.host_id, AppRow.name == patch.name, AppRow.id != row.id)
            .one_or_none()
        )
        if existing is not None:
            raise ValueError(f"App '{patch.name}' existiert bereits auf diesem Host")
        row.name = patch.name
    if patch.description is not None:
        row.description = patch.description
    if patch.container_filter is not None:
        row.container_filter = patch.container_filter
    if patch.compose_path is not None:
        row.compose_path = patch.compose_path
    if patch.healthcheck_url is not None:
        row.healthcheck_url = patch.healthcheck_url
    if patch.tags is not None:
        row.tags = json.dumps(patch.tags)
    if patch.enabled is not None:
        row.enabled = int(patch.enabled)
    row.updated_at = _iso_now()
    session.commit()
    audit.write(session, action="app.update", target=row.id, before=before, after={
        "name": row.name, "container_filter": row.container_filter, "enabled": bool(row.enabled),
    }, ip=ip)
    return row


def delete_app(session: Session, app_id: str, *, ip: str | None = None) -> bool:
    row = get_app(session, app_id)
    if row is None:
        return False
    name = row.name
    session.delete(row)
    session.commit()
    audit.write(session, action="app.delete", target=app_id, before={"name": name}, ip=ip)
    return True


def update_status(
    session: Session,
    app_id: str,
    *,
    status: str,
    summary: dict | None = None,
) -> AppRow | None:
    row = get_app(session, app_id)
    if row is None:
        return None
    row.last_status = status
    row.last_check_at = _iso_now()
    row.last_summary = json.dumps(summary or {})
    row.updated_at = _iso_now()
    session.commit()
    return row
