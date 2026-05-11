"""Bootstrap: Default-Hosts und Default-Apps in die DB einspielen.

Idempotent. Wird beim Start aufgerufen.
"""
from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from ..config import CockpitConfig
from ..crud import apps as crud_apps
from ..crud import hosts as crud_hosts
from ..models import AppCreate, HostCreate

log = logging.getLogger(__name__)


# Bekannte Apps pro Host (Filter sind docker-ps --filter Werte)
DEFAULT_APPS: list[dict] = [
    # NUC
    {"host": "nuc", "name": "auditworkshop", "container_filter": "name=auditworkshop-",
     "compose_path": "/home/janpow/Projekte/Workshop/auditworkshop/docker-compose.yml",
     "tags": ["workshop", "demo"]},
    {"host": "nuc", "name": "audit_designer", "container_filter": "name=audit_designer",
     "compose_path": "/home/janpow/Projekte/audit_designer/docker-compose.yml",
     "tags": ["main", "audit"]},
    {"host": "nuc", "name": "flowinvoice", "container_filter": "name=flowinvoice",
     "tags": ["service"]},
    {"host": "nuc", "name": "hpp", "container_filter": "name=hpp-",
     "tags": ["regulierung"]},
    {"host": "nuc", "name": "qaaudit", "container_filter": "name=qaaudit-",
     "tags": ["audit"]},
    {"host": "nuc", "name": "backfill", "container_filter": "name=backfill-",
     "tags": ["sidecar", "data-load"]},
    # CCX23
    {"host": "ccx23", "name": "auditworkshop", "container_filter": "name=auditworkshop-",
     "compose_path": "/opt/auditworkshop/compose.yaml",
     "healthcheck_url": "http://127.0.0.1:3004/",
     "tags": ["workshop", "public"]},
    {"host": "ccx23", "name": "llm-router", "container_filter": "name=llm-router",
     "compose_path": "/opt/llm-router/compose.yaml",
     "healthcheck_url": "http://100.99.159.80:7842/health",
     "tags": ["service", "llm"]},
    {"host": "ccx23", "name": "checklist", "container_filter": "name=checklist",
     "compose_path": "/opt/checklist/compose.yaml",
     "tags": ["main", "audit"]},
]


def bootstrap_hosts(session: Session, config: CockpitConfig) -> int:
    """Importiert YAML-Hosts in die DB. Idempotent."""
    created = 0
    for h in config.hosts:
        existing = crud_hosts.get_host_by_name(session, h.name)
        if existing:
            continue
        try:
            crud_hosts.create_host(
                session,
                HostCreate(
                    name=h.name,
                    tailscale_ip=h.tailscale_ip,
                    description=h.description,
                    ssh_user=h.ssh_user,
                    ssh_key_path=h.ssh_key_path,
                    is_self=h.is_self,
                ),
            )
            created += 1
        except Exception as exc:  # noqa: BLE001
            log.warning("Bootstrap-Host '%s' fehlgeschlagen: %s", h.name, exc)
    return created


def bootstrap_apps(session: Session) -> int:
    """Legt die Default-Apps an, sofern der zugehoerige Host existiert."""
    created = 0
    for entry in DEFAULT_APPS:
        host = crud_hosts.get_host_by_name(session, entry["host"])
        if host is None:
            continue
        existing = (
            session.query(crud_apps.AppRow)
            .filter(crud_apps.AppRow.host_id == host.id, crud_apps.AppRow.name == entry["name"])
            .one_or_none()
        )
        if existing:
            continue
        try:
            crud_apps.create_app(
                session,
                AppCreate(
                    host_id=host.id,
                    name=entry["name"],
                    description=entry.get("description", ""),
                    container_filter=entry.get("container_filter", ""),
                    compose_path=entry.get("compose_path"),
                    healthcheck_url=entry.get("healthcheck_url"),
                    tags=entry.get("tags", []),
                ),
            )
            created += 1
        except Exception as exc:  # noqa: BLE001
            log.warning("Bootstrap-App '%s' fehlgeschlagen: %s", entry["name"], exc)
    return created
