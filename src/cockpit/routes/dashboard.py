"""Dashboard-Aggregationen."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..auth import require_auth
from ..crud import apps as crud_apps
from ..crud import audit as crud_audit
from ..crud import backups as crud_backups
from ..crud import github_repos as crud_repos
from ..crud import hosts as crud_hosts
from ..crud import secrets as crud_secrets
from ..db import get_session
from ..models import DashboardStats, audit_row_to_out

router = APIRouter(prefix="/admin/api/dashboard", tags=["dashboard"])


@router.get("", response_model=DashboardStats)
async def dashboard(_=Depends(require_auth), session: Session = Depends(get_session)) -> DashboardStats:
    apps = crud_apps.list_apps(session)
    hosts = crud_hosts.list_hosts(session)
    backups = crud_backups.list_backups(session)
    secrets = crud_secrets.list_secrets(session)
    repos = crud_repos.list_repos(session)
    recent_audit = crud_audit.list_audit(session, limit=10)

    apps_total = len(apps)
    apps_healthy = sum(1 for a in apps if a.last_status == "healthy")
    apps_down = sum(1 for a in apps if a.last_status == "down")
    apps_unknown = sum(1 for a in apps if a.last_status in ("unknown", "degraded"))

    hosts_total = len(hosts)
    hosts_online = sum(1 for h in hosts if h.last_status == "online")

    last_backup = None
    last_backup_status = None
    for b in sorted(backups, key=lambda b: b.last_run_at or "", reverse=True):
        if b.last_run_at:
            last_backup = b.last_run_at
            last_backup_status = b.last_run_status
            break

    return DashboardStats(
        apps_total=apps_total,
        apps_healthy=apps_healthy,
        apps_down=apps_down,
        apps_unknown=apps_unknown,
        hosts_total=hosts_total,
        hosts_online=hosts_online,
        last_backup_at=_parse(last_backup),
        last_backup_status=last_backup_status,
        backups_total=len(backups),
        secrets_total=len(secrets),
        repos_total=len(repos),
        recent_audit=[audit_row_to_out(r) for r in recent_audit],
    )


def _parse(s):
    if not s:
        return None
    from datetime import datetime
    try:
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        return datetime.fromisoformat(s)
    except ValueError:
        return None
