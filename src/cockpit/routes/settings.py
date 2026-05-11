"""Settings-Endpoints."""
from __future__ import annotations

import json
import time
from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from .. import __version__
from ..auth import require_auth
from ..config import load_config
from ..db import get_session
from ..models import SettingRow, SettingsOut, SettingsUpdate
from ..services import github_client
from ..services.secret_vault import is_enabled as vault_enabled

router = APIRouter(prefix="/admin/api/settings", tags=["settings"])

_STARTED_AT = time.time()


def _read_setting(session: Session, key: str, default: Any) -> Any:
    row = session.get(SettingRow, key)
    if row is None:
        return default
    try:
        return json.loads(row.value)
    except (json.JSONDecodeError, TypeError):
        return default


def _write_setting(session: Session, key: str, value: Any) -> None:
    row = session.get(SettingRow, key)
    payload = json.dumps(value)
    if row is None:
        session.add(SettingRow(key=key, value=payload))
    else:
        row.value = payload
    session.commit()


def _build_settings(session: Session) -> SettingsOut:
    cfg = load_config()
    return SettingsOut(
        cockpit_version=__version__,
        uptime_seconds=int(time.time() - _STARTED_AT),
        self_host_name=cfg.self_host_name,
        data_dir=cfg.data_dir,
        config_path=cfg.config_path,
        vault_enabled=vault_enabled(),
        github_enabled=github_client.is_enabled(),
        admin_password_is_default=cfg.admin_password_is_default,
        health_interval_s=int(_read_setting(session, "health_interval_s", 60)),
    )


@router.get("", response_model=SettingsOut)
async def get_settings(_=Depends(require_auth), session: Session = Depends(get_session)) -> SettingsOut:
    return _build_settings(session)


@router.patch("", response_model=SettingsOut)
async def patch_settings(
    patch: SettingsUpdate,
    _=Depends(require_auth),
    session: Session = Depends(get_session),
) -> SettingsOut:
    if patch.health_interval_s is not None:
        _write_setting(session, "health_interval_s", patch.health_interval_s)
    return _build_settings(session)
