"""CRUD fuer Deployment-Historie."""
from __future__ import annotations

import secrets
import time
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from ..models import (
    AppRow,
    DeploymentCreate,
    DeploymentRow,
)
from . import audit


def _new_id() -> str:
    return f"dp_{int(time.time() * 1000):x}_{secrets.token_hex(3)}"


def _iso_now() -> str:
    return datetime.now(tz=UTC).isoformat().replace("+00:00", "Z")


def create(
    session: Session,
    app_id: str,
    payload: DeploymentCreate,
    *,
    ip: str | None = None,
) -> DeploymentRow:
    if session.get(AppRow, app_id) is None:
        raise ValueError(f"app_id unbekannt: {app_id}")
    ts_iso = (payload.ts or datetime.now(tz=UTC)).astimezone(UTC).isoformat().replace("+00:00", "Z")
    row = DeploymentRow(
        id=_new_id(),
        app_id=app_id,
        ts=ts_iso,
        image=payload.image,
        image_digest=payload.image_digest,
        git_sha=payload.git_sha,
        source=payload.source,
        actor=payload.actor or "admin",
        status=payload.status,
        notes=payload.notes,
        duration_s=payload.duration_s,
        created_at=_iso_now(),
    )
    session.add(row)
    session.flush()
    audit.write(
        session,
        action="deployment.record",
        target=app_id,
        after={
            "image": row.image,
            "git_sha": row.git_sha,
            "source": row.source,
            "status": row.status,
        },
        actor=row.actor,
        ip=ip,
        commit=False,
    )
    session.commit()
    return row


def list_for_app(session: Session, app_id: str, *, limit: int = 50) -> list[DeploymentRow]:
    return (
        session.query(DeploymentRow)
        .filter(DeploymentRow.app_id == app_id)
        .order_by(DeploymentRow.ts.desc())
        .limit(limit)
        .all()
    )


def list_recent(session: Session, *, limit: int = 50) -> list[DeploymentRow]:
    return (
        session.query(DeploymentRow)
        .order_by(DeploymentRow.ts.desc())
        .limit(limit)
        .all()
    )


def current_for_app(session: Session, app_id: str) -> DeploymentRow | None:
    return (
        session.query(DeploymentRow)
        .filter(DeploymentRow.app_id == app_id)
        .filter(DeploymentRow.status.in_(["ok", "started"]))
        .order_by(DeploymentRow.ts.desc())
        .first()
    )
