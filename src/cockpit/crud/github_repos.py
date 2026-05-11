"""GitHub-Repo-Bookmarks (CRUD). Daten kommen live aus api.github.com."""
from __future__ import annotations

import secrets
import time
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from ..models import RepoCreate, RepoRow, RepoUpdate
from . import audit


def _new_id() -> str:
    return f"r_{int(time.time() * 1000):x}_{secrets.token_hex(3)}"


def _iso_now() -> str:
    return datetime.now(tz=UTC).isoformat().replace("+00:00", "Z")


def list_repos(session: Session) -> list[RepoRow]:
    return session.query(RepoRow).order_by(RepoRow.owner.asc(), RepoRow.name.asc()).all()


def get_repo(session: Session, repo_id: str) -> RepoRow | None:
    return session.get(RepoRow, repo_id)


def get_by_full_name(session: Session, owner: str, name: str) -> RepoRow | None:
    return session.query(RepoRow).filter(RepoRow.owner == owner, RepoRow.name == name).one_or_none()


def create_repo(session: Session, payload: RepoCreate, *, ip: str | None = None) -> RepoRow:
    if get_by_full_name(session, payload.owner, payload.name):
        raise ValueError(f"Repo '{payload.owner}/{payload.name}' existiert bereits")
    now = _iso_now()
    row = RepoRow(
        id=_new_id(),
        owner=payload.owner,
        name=payload.name,
        description=payload.description,
        default_branch=payload.default_branch,
        enabled=int(payload.enabled),
        created_at=now,
        updated_at=now,
    )
    session.add(row)
    session.commit()
    audit.write(session, action="repo.create", target=row.id, after={"full_name": f"{row.owner}/{row.name}"}, ip=ip)
    return row


def update_repo(session: Session, repo_id: str, patch: RepoUpdate, *, ip: str | None = None) -> RepoRow | None:
    row = get_repo(session, repo_id)
    if row is None:
        return None
    before = {"description": row.description, "enabled": bool(row.enabled)}
    if patch.description is not None:
        row.description = patch.description
    if patch.default_branch is not None:
        row.default_branch = patch.default_branch
    if patch.enabled is not None:
        row.enabled = int(patch.enabled)
    row.updated_at = _iso_now()
    session.commit()
    audit.write(session, action="repo.update", target=row.id, before=before, after={
        "description": row.description, "enabled": bool(row.enabled),
    }, ip=ip)
    return row


def delete_repo(session: Session, repo_id: str, *, ip: str | None = None) -> bool:
    row = get_repo(session, repo_id)
    if row is None:
        return False
    fname = f"{row.owner}/{row.name}"
    session.delete(row)
    session.commit()
    audit.write(session, action="repo.delete", target=repo_id, before={"full_name": fname}, ip=ip)
    return True


def mark_synced(session: Session, repo_id: str) -> None:
    row = get_repo(session, repo_id)
    if row is None:
        return
    row.last_sync_at = _iso_now()
    session.commit()
