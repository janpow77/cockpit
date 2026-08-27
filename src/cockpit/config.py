"""Konfigurations-Layer fuer das Cockpit.

Ein-Datei-Modul. Liest:
- Env-Variablen (Bearer-Token, Vault-Key, GitHub-Token, DB-Pfad)
- Optionale YAML-Datei (Hosts-Bootstrap)

Die YAML wird **nur beim ersten Start** in die DB importiert. Danach ist die
DB authoritative.
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

log = logging.getLogger(__name__)


@dataclass
class HostBootstrap:
    name: str
    tailscale_ip: str
    description: str = ""
    ssh_user: str | None = None
    ssh_key_path: str | None = None
    is_self: bool = False

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> HostBootstrap:
        return cls(
            name=str(raw["name"]).strip(),
            tailscale_ip=str(raw["tailscale_ip"]).strip(),
            description=str(raw.get("description") or ""),
            ssh_user=raw.get("ssh_user"),
            ssh_key_path=raw.get("ssh_key_path"),
            is_self=bool(raw.get("is_self", False)),
        )


@dataclass
class CockpitConfig:
    hosts: list[HostBootstrap] = field(default_factory=list)
    admin_password: str = "cockpit-admin"
    admin_password_is_default: bool = True
    vault_key: str | None = None
    github_token: str | None = None
    db_path: str = "/data/cockpit.db"
    data_dir: str = "/data"
    config_path: str = ""
    self_host_name: str = "ccx23"
    port: int = 7843


def _load_yaml(path: str) -> dict:
    p = Path(path)
    if not p.exists():
        log.info("Config-Datei nicht gefunden: %s — nur Env-Konfig wird genutzt.", path)
        return {}
    try:
        with p.open("r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except Exception as exc:  # noqa: BLE001
        log.warning("Konnte Config-YAML nicht parsen (%s): %s", path, exc)
        return {}


def load_config() -> CockpitConfig:
    """Sammelt Konfiguration aus Env + optionaler YAML."""
    cfg_path = os.environ.get("COCKPIT_CONFIG", "/etc/cockpit/config.yaml")
    raw = _load_yaml(cfg_path)

    hosts: list[HostBootstrap] = []
    for h in raw.get("hosts") or []:
        try:
            hosts.append(HostBootstrap.from_dict(h))
        except Exception as exc:  # noqa: BLE001
            log.warning("Host-Eintrag ignoriert (%s): %s", h, exc)

    admin_pw_env = os.environ.get("COCKPIT_ADMIN_PASSWORD")
    admin_pw = admin_pw_env or "cockpit-admin"
    if not admin_pw_env:
        log.warning(
            "COCKPIT_ADMIN_PASSWORD nicht gesetzt — fallback 'cockpit-admin' (NUR FUER LOKALE TESTS!)"
        )

    return CockpitConfig(
        hosts=hosts,
        admin_password=admin_pw,
        admin_password_is_default=not admin_pw_env,
        vault_key=os.environ.get("COCKPIT_VAULT_KEY"),
        github_token=os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN"),
        db_path=os.environ.get("ADMIN_DB_PATH", "/data/cockpit.db"),
        data_dir=os.environ.get("COCKPIT_DATA_DIR", "/data"),
        config_path=cfg_path,
        self_host_name=os.environ.get("COCKPIT_SELF_HOST", "ccx23"),
        port=int(os.environ.get("COCKPIT_PORT", "7843")),
    )
