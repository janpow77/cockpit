"""Audit-Log: jede mutierende Aktion landet hier."""
from __future__ import annotations

import json
import secrets
import time
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

from ..models import AuditRow


def _new_id() -> str:
    return f"a_{int(time.time() * 1000):x}_{secrets.token_hex(4)}"


def _iso_now() -> str:
    return datetime.now(tz=UTC).isoformat().replace("+00:00", "Z")


def _serialize(payload: Any) -> str | None:
    if payload is None:
        return None
    try:
        return json.dumps(payload, ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        return json.dumps({"_repr": repr(payload)})


def write(
    session: Session,
    *,
    action: str,
    target: str | None = None,
    before: Any = None,
    after: Any = None,
    actor: str = "admin",
    ip: str | None = None,
    notes: str | None = None,
    commit: bool = True,
) -> AuditRow:
    row = AuditRow(
        id=_new_id(),
        ts=_iso_now(),
        actor=actor,
        action=action,
        target=target,
        before=_serialize(before),
        after=_serialize(after),
        ip=ip,
        notes=notes,
    )
    session.add(row)
    if commit:
        session.commit()
    return row


def list_audit(
    session: Session,
    *,
    actor: str | None = None,
    action: str | None = None,
    target: str | None = None,
    since: str | None = None,
    limit: int = 200,
) -> list[AuditRow]:
    q = session.query(AuditRow)
    if actor:
        q = q.filter(AuditRow.actor == actor)
    if action:
        q = q.filter(AuditRow.action.ilike(f"%{action}%"))
    if target:
        q = q.filter(AuditRow.target.ilike(f"%{target}%"))
    if since:
        q = q.filter(AuditRow.ts >= since)
    return q.order_by(AuditRow.ts.desc()).limit(limit).all()
