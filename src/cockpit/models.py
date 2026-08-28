"""ORM-Modelle (SQLAlchemy 2.0) und Pydantic-Schemas.

ORM-Modelle bilden die Tabellen aus ``migrations/001_initial.sql`` ab.
Pydantic-Schemas werden in der Router-Schicht fuer Request/Response benutzt.
"""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import Column, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import declarative_base

Base = declarative_base()


# ----------------------------- ORM ----------------------------------------


class HostRow(Base):
    __tablename__ = "cockpit_hosts"

    id = Column(String, primary_key=True)
    name = Column(String, unique=True, nullable=False)
    tailscale_ip = Column(String, nullable=False)
    description = Column(Text, nullable=False, default="")
    ssh_user = Column(String, nullable=True)
    ssh_key_path = Column(String, nullable=True)
    is_self = Column(Integer, nullable=False, default=0)
    enabled = Column(Integer, nullable=False, default=1)
    last_check_at = Column(String, nullable=True)
    last_status = Column(String, nullable=False, default="unknown")
    last_error = Column(String, nullable=True)
    created_at = Column(String, nullable=False)
    updated_at = Column(String, nullable=False)


class AppRow(Base):
    __tablename__ = "cockpit_apps"

    id = Column(String, primary_key=True)
    host_id = Column(String, ForeignKey("cockpit_hosts.id", ondelete="CASCADE"), nullable=False)
    name = Column(String, nullable=False)
    description = Column(Text, nullable=False, default="")
    container_filter = Column(Text, nullable=False, default="")
    compose_path = Column(String, nullable=True)
    healthcheck_url = Column(String, nullable=True)
    tags = Column(Text, nullable=False, default="[]")
    enabled = Column(Integer, nullable=False, default=1)
    last_check_at = Column(String, nullable=True)
    last_status = Column(String, nullable=False, default="unknown")
    last_summary = Column(Text, nullable=True)
    created_at = Column(String, nullable=False)
    updated_at = Column(String, nullable=False)


class RepoRow(Base):
    __tablename__ = "cockpit_repos"

    id = Column(String, primary_key=True)
    owner = Column(String, nullable=False)
    name = Column(String, nullable=False)
    description = Column(Text, nullable=False, default="")
    default_branch = Column(String, nullable=False, default="main")
    enabled = Column(Integer, nullable=False, default=1)
    last_sync_at = Column(String, nullable=True)
    created_at = Column(String, nullable=False)
    updated_at = Column(String, nullable=False)


class BackupRow(Base):
    __tablename__ = "cockpit_backups"

    id = Column(String, primary_key=True)
    name = Column(String, unique=True, nullable=False)
    host_id = Column(String, ForeignKey("cockpit_hosts.id", ondelete="CASCADE"), nullable=False)
    backup_type = Column(String, nullable=False, default="shell")
    command = Column(Text, nullable=False)
    target_path = Column(String, nullable=False)
    schedule_cron = Column(String, nullable=True)
    enabled = Column(Integer, nullable=False, default=1)
    last_run_at = Column(String, nullable=True)
    last_run_status = Column(String, nullable=False, default="never")
    last_size_bytes = Column(Integer, nullable=True)
    last_run_log = Column(Text, nullable=True)
    created_at = Column(String, nullable=False)
    updated_at = Column(String, nullable=False)


class SecretRow(Base):
    __tablename__ = "cockpit_secrets"

    id = Column(String, primary_key=True)
    key = Column(String, unique=True, nullable=False)
    value_encrypted = Column(Text, nullable=False)
    app_tag = Column(String, nullable=True)
    host_tag = Column(String, nullable=True)
    comment = Column(Text, nullable=False, default="")
    last_used_at = Column(String, nullable=True)
    last_used_purpose = Column(String, nullable=True)
    reveal_count = Column(Integer, nullable=False, default=0)
    created_at = Column(String, nullable=False)
    updated_at = Column(String, nullable=False)


class AuditRow(Base):
    __tablename__ = "cockpit_audit"

    id = Column(String, primary_key=True)
    ts = Column(String, nullable=False)
    actor = Column(String, nullable=False, default="admin")
    action = Column(String, nullable=False)
    target = Column(String, nullable=True)
    before = Column(Text, nullable=True)
    after = Column(Text, nullable=True)
    ip = Column(String, nullable=True)
    notes = Column(Text, nullable=True)


class SettingRow(Base):
    __tablename__ = "cockpit_settings"

    key = Column(String, primary_key=True)
    value = Column(Text, nullable=False)


class SessionRow(Base):
    __tablename__ = "cockpit_sessions"

    token = Column(String, primary_key=True)
    actor = Column(String, nullable=False, default="admin")
    created_at = Column(String, nullable=False)
    expires_at = Column(String, nullable=False)
    last_seen_at = Column(String, nullable=False)
    ip = Column(String, nullable=True)


class AuftragRow(Base):
    """Kanban-Auftrag: ein Agentenlauf (Claude/Codex/Gemini) in einem Worktree (services/auftraege.py)."""

    __tablename__ = "cockpit_auftraege"

    id = Column(String, primary_key=True)
    titel = Column(String, nullable=False)
    text = Column(Text, nullable=False)
    host = Column(String, nullable=False)
    projekt = Column(String, nullable=False)
    projekt_name = Column(String, nullable=False, default="")
    agent = Column(String, nullable=False, default="claude")
    modus = Column(String, nullable=False, default="umsetzen")  # bericht | plan_freigabe | umsetzen
    freigegeben = Column(String, nullable=True)  # Zeitpunkt der Freigabe (Modus plan_freigabe)
    profil = Column(String, nullable=False, default="bearbeiten")
    prioritaet = Column(Integer, nullable=False, default=3)
    zeitfenster = Column(String, nullable=False, default="sofort")
    status = Column(String, nullable=False, default="eingang")
    reihenfolge = Column(Integer, nullable=False, default=0)
    branch = Column(String, nullable=True)
    worktree = Column(String, nullable=True)
    session_id = Column(String, nullable=True)
    gestartet = Column(String, nullable=True)
    beendet = Column(String, nullable=True)
    dauer_s = Column(Integer, nullable=True)
    ergebnis = Column(Text, nullable=True)
    fehler = Column(Text, nullable=True)
    kosten_usd = Column(Float, nullable=True)
    tokens_in = Column(Integer, nullable=True)
    tokens_out = Column(Integer, nullable=True)
    turns = Column(Integer, nullable=True)
    letzte_zeile = Column(String, nullable=True)
    diff_url = Column(String, nullable=True)
    pruefung = Column(Text, nullable=True)  # JSON: [{befehl, ok, dauer_s, auszug}] – Qualitätstor im Worktree
    pruefung_ok = Column(Integer, nullable=True)  # 1 = alle Prüfbefehle grün, 0 = mindestens einer rot
    pr_url = Column(String, nullable=True)
    pr_checks = Column(String, nullable=True)  # Kurzstand der GitHub-Checks (gh pr checks)
    erstellt = Column(String, nullable=False)
    aktualisiert = Column(String, nullable=False)


class WallSampleRow(Base):
    """Verlauf der Wand: ein Wert je Kennzahl und Lauf (services/verlauf.py)."""

    __tablename__ = "cockpit_wall_samples"
    __table_args__ = (Index("ix_wall_samples_key_ts", "key", "ts"),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    ts = Column(String, nullable=False)
    key = Column(String, nullable=False)
    value = Column(Float, nullable=False)


class TrafficSampleRow(Base):
    __tablename__ = "cockpit_traffic_samples"

    id = Column(String, primary_key=True)
    bucket_ts = Column(String, nullable=False)
    bucket_size = Column(String, nullable=False, default="1m")
    app_id = Column(String, ForeignKey("cockpit_apps.id", ondelete="SET NULL"), nullable=True)
    host_id = Column(String, ForeignKey("cockpit_hosts.id", ondelete="CASCADE"), nullable=False)
    server_name = Column(String, nullable=True)
    requests = Column(Integer, nullable=False, default=0)
    status_2xx = Column(Integer, nullable=False, default=0)
    status_3xx = Column(Integer, nullable=False, default=0)
    status_4xx = Column(Integer, nullable=False, default=0)
    status_5xx = Column(Integer, nullable=False, default=0)
    bytes_out = Column(Integer, nullable=False, default=0)
    latency_p50_ms = Column(Integer, nullable=True)
    latency_p95_ms = Column(Integer, nullable=True)
    latency_max_ms = Column(Integer, nullable=True)
    created_at = Column(String, nullable=False)


class TrafficSourceRow(Base):
    __tablename__ = "cockpit_traffic_sources"

    id = Column(String, primary_key=True)
    host_id = Column(String, ForeignKey("cockpit_hosts.id", ondelete="CASCADE"), nullable=False)
    log_path = Column(String, nullable=False)
    log_format = Column(String, nullable=False, default="caddy_json")
    server_app_map = Column(Text, nullable=False, default="[]")
    last_offset = Column(Integer, nullable=False, default=0)
    last_inode = Column(String, nullable=True)
    last_collect_at = Column(String, nullable=True)
    last_status = Column(String, nullable=False, default="never")
    last_error = Column(String, nullable=True)
    enabled = Column(Integer, nullable=False, default=1)
    created_at = Column(String, nullable=False)
    updated_at = Column(String, nullable=False)


class DeploymentRow(Base):
    __tablename__ = "cockpit_deployments"

    id = Column(String, primary_key=True)
    app_id = Column(String, ForeignKey("cockpit_apps.id", ondelete="CASCADE"), nullable=False)
    ts = Column(String, nullable=False)
    image = Column(String, nullable=False)
    image_digest = Column(String, nullable=True)
    git_sha = Column(String, nullable=True)
    source = Column(String, nullable=False, default="unknown")
    actor = Column(String, nullable=False, default="system")
    status = Column(String, nullable=False, default="ok")
    notes = Column(Text, nullable=True)
    duration_s = Column(Integer, nullable=True)
    created_at = Column(String, nullable=False)


# ----------------------------- Pydantic ------------------------------------


# --------- Auth ---------
class LoginRequest(BaseModel):
    username: str | None = None  # fehlt -> "admin" (Skripte, Altbestand)
    password: str


class LoginResponse(BaseModel):
    token: str
    expires_at: datetime


class MeResponse(BaseModel):
    logged_in: bool
    expires_at: datetime | None = None


# --------- Hosts ---------
class HostCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    tailscale_ip: str = Field(min_length=1)
    description: str = ""
    ssh_user: str | None = None
    ssh_key_path: str | None = None
    is_self: bool = False
    enabled: bool = True

    @field_validator("name")
    @classmethod
    def _strip(cls, v: str) -> str:
        return v.strip()


class HostUpdate(BaseModel):
    name: str | None = None
    tailscale_ip: str | None = None
    description: str | None = None
    ssh_user: str | None = None
    ssh_key_path: str | None = None
    is_self: bool | None = None
    enabled: bool | None = None


class HostOut(BaseModel):
    id: str
    name: str
    tailscale_ip: str
    description: str
    ssh_user: str | None = None
    ssh_key_path: str | None = None
    is_self: bool
    enabled: bool
    last_check_at: datetime | None = None
    last_status: str
    last_error: str | None = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


# --------- Apps ---------
class AppCreate(BaseModel):
    host_id: str = Field(min_length=1)
    name: str = Field(min_length=1, max_length=120)
    description: str = ""
    container_filter: str = ""
    compose_path: str | None = None
    healthcheck_url: str | None = None
    tags: list[str] = Field(default_factory=list)
    enabled: bool = True


class AppUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    container_filter: str | None = None
    compose_path: str | None = None
    healthcheck_url: str | None = None
    tags: list[str] | None = None
    enabled: bool | None = None


class ContainerInfo(BaseModel):
    name: str
    image: str = ""
    state: str = ""
    status: str = ""
    ports: str = ""


class AppOut(BaseModel):
    id: str
    host_id: str
    host_name: str
    name: str
    description: str
    container_filter: str
    compose_path: str | None = None
    healthcheck_url: str | None = None
    tags: list[str] = Field(default_factory=list)
    enabled: bool
    last_check_at: datetime | None = None
    last_status: str
    container_count: int = 0
    healthy_count: int = 0
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AppDetail(AppOut):
    containers: list[ContainerInfo] = Field(default_factory=list)
    health_http: dict[str, Any] | None = None


# --------- GitHub ---------
class RepoCreate(BaseModel):
    owner: str = Field(min_length=1)
    name: str = Field(min_length=1)
    description: str = ""
    default_branch: str = "main"
    enabled: bool = True


class RepoUpdate(BaseModel):
    description: str | None = None
    default_branch: str | None = None
    enabled: bool | None = None


class RepoOut(BaseModel):
    id: str
    owner: str
    name: str
    description: str
    default_branch: str
    enabled: bool
    last_sync_at: datetime | None = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


# --------- Backups ---------
BackupKind = Literal["postgres", "rsync", "docker_volume", "shell"]


class BackupCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    host_id: str = Field(min_length=1)
    backup_type: BackupKind = "shell"
    command: str = Field(min_length=1)
    target_path: str = Field(min_length=1)
    schedule_cron: str | None = None
    enabled: bool = True


class BackupUpdate(BaseModel):
    name: str | None = None
    backup_type: BackupKind | None = None
    command: str | None = None
    target_path: str | None = None
    schedule_cron: str | None = None
    enabled: bool | None = None


class BackupOut(BaseModel):
    id: str
    name: str
    host_id: str
    host_name: str
    backup_type: str
    command: str
    target_path: str
    schedule_cron: str | None = None
    enabled: bool
    last_run_at: datetime | None = None
    last_run_status: str
    last_size_bytes: int | None = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class BackupRunResult(BaseModel):
    ok: bool
    duration_ms: int
    bytes: int | None = None
    log: str = ""
    error: str | None = None


# --------- Secrets ---------
class SecretCreate(BaseModel):
    key: str = Field(min_length=1, max_length=200)
    value: str = Field(min_length=1)
    app_tag: str | None = None
    host_tag: str | None = None
    comment: str = ""

    @field_validator("key")
    @classmethod
    def _strip_key(cls, v: str) -> str:
        return v.strip()


class SecretUpdate(BaseModel):
    value: str | None = None
    app_tag: str | None = None
    host_tag: str | None = None
    comment: str | None = None


class SecretOut(BaseModel):
    """Listen-Eintrag — KEIN Wert."""

    id: str
    key: str
    app_tag: str | None = None
    host_tag: str | None = None
    comment: str
    last_used_at: datetime | None = None
    last_used_purpose: str | None = None
    reveal_count: int
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class SecretRevealRequest(BaseModel):
    purpose: str = Field(min_length=1, max_length=500)


class SecretRevealResponse(BaseModel):
    id: str
    key: str
    value: str
    revealed_at: datetime
    purpose: str


# --------- Audit ---------
class AuditOut(BaseModel):
    id: str
    ts: datetime
    actor: str
    action: str
    target: str | None = None
    before: dict | list | None = None
    after: dict | list | None = None
    ip: str | None = None
    notes: str | None = None

    model_config = ConfigDict(from_attributes=True)


# --------- Dashboard ---------
class DashboardStats(BaseModel):
    apps_total: int
    apps_healthy: int
    apps_down: int
    apps_unknown: int
    hosts_total: int
    hosts_online: int
    last_backup_at: datetime | None = None
    last_backup_status: str | None = None
    backups_total: int
    secrets_total: int
    repos_total: int
    recent_audit: list[AuditOut] = Field(default_factory=list)


# --------- Settings ---------
class SettingsOut(BaseModel):
    cockpit_version: str
    uptime_seconds: int
    self_host_name: str
    data_dir: str
    config_path: str
    vault_enabled: bool
    github_enabled: bool
    admin_password_is_default: bool
    health_interval_s: int = 60


class SettingsUpdate(BaseModel):
    health_interval_s: int | None = Field(default=None, ge=10, le=3600)


# --------- Traffic ---------
TrafficBucketSize = Literal["1m", "5m", "1h", "1d"]


class TrafficSourceCreate(BaseModel):
    host_id: str = Field(min_length=1)
    log_path: str = Field(min_length=1)
    log_format: str = "caddy_json"
    server_app_map: list[dict] = Field(default_factory=list)
    enabled: bool = True


class TrafficSourceUpdate(BaseModel):
    log_path: str | None = None
    log_format: str | None = None
    server_app_map: list[dict] | None = None
    enabled: bool | None = None


class TrafficSourceOut(BaseModel):
    id: str
    host_id: str
    host_name: str
    log_path: str
    log_format: str
    server_app_map: list[dict] = Field(default_factory=list)
    last_collect_at: datetime | None = None
    last_status: str
    last_error: str | None = None
    enabled: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class TrafficPoint(BaseModel):
    bucket_ts: datetime
    requests: int = 0
    status_2xx: int = 0
    status_3xx: int = 0
    status_4xx: int = 0
    status_5xx: int = 0
    bytes_out: int = 0
    latency_p50_ms: int | None = None
    latency_p95_ms: int | None = None
    latency_max_ms: int | None = None


class TrafficSeriesResponse(BaseModel):
    bucket_size: TrafficBucketSize
    app_id: str | None = None
    host_id: str | None = None
    from_ts: datetime
    to_ts: datetime
    total_requests: int = 0
    error_rate: float = 0.0
    points: list[TrafficPoint] = Field(default_factory=list)


# --------- Deployments ---------
DeploymentSource = Literal["lifecycle", "gh-action", "manual", "unknown"]
DeploymentStatus = Literal["ok", "failed", "started", "rolled_back"]


class DeploymentCreate(BaseModel):
    image: str = Field(min_length=1, max_length=500)
    image_digest: str | None = None
    git_sha: str | None = None
    source: DeploymentSource = "manual"
    actor: str = "admin"
    status: DeploymentStatus = "ok"
    notes: str | None = None
    duration_s: int | None = Field(default=None, ge=0)
    # Optional: ts kann vom Caller gesetzt werden (lifecycle/start.sh schickt
    # ggf. den Zeitpunkt des compose-up, nicht den HTTP-Request).
    ts: datetime | None = None


class DeploymentOut(BaseModel):
    id: str
    app_id: str
    app_name: str
    ts: datetime
    image: str
    image_digest: str | None = None
    git_sha: str | None = None
    source: str
    actor: str
    status: str
    notes: str | None = None
    duration_s: int | None = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ----------------------------- Konvertierung ------------------------------


def _decode_json_list(raw: str | None, default: list) -> list:
    if not raw:
        return list(default)
    try:
        out = json.loads(raw)
        return out if isinstance(out, list) else list(default)
    except (TypeError, ValueError):
        return list(default)


def _decode_json(raw: str | None) -> dict | list | None:
    if raw is None:
        return None
    try:
        return json.loads(raw)
    except (TypeError, ValueError):
        return None


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        if value.endswith("Z"):
            value = value[:-1] + "+00:00"
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _parse_dt_required(value: str | None) -> datetime:
    return _parse_dt(value) or datetime.fromtimestamp(0)


def host_row_to_out(row: HostRow) -> HostOut:
    return HostOut(
        id=row.id,
        name=row.name,
        tailscale_ip=row.tailscale_ip,
        description=row.description or "",
        ssh_user=row.ssh_user,
        ssh_key_path=row.ssh_key_path,
        is_self=bool(row.is_self),
        enabled=bool(row.enabled),
        last_check_at=_parse_dt(row.last_check_at),
        last_status=row.last_status,
        last_error=row.last_error,
        created_at=_parse_dt_required(row.created_at),
        updated_at=_parse_dt_required(row.updated_at),
    )


def app_row_to_out(row: AppRow, *, host_name: str, summary: dict | None = None) -> AppOut:
    summary = summary or _decode_json(row.last_summary) or {}
    return AppOut(
        id=row.id,
        host_id=row.host_id,
        host_name=host_name,
        name=row.name,
        description=row.description or "",
        container_filter=row.container_filter or "",
        compose_path=row.compose_path,
        healthcheck_url=row.healthcheck_url,
        tags=_decode_json_list(row.tags, []),
        enabled=bool(row.enabled),
        last_check_at=_parse_dt(row.last_check_at),
        last_status=row.last_status,
        container_count=int(summary.get("container_count") or 0),
        healthy_count=int(summary.get("healthy_count") or 0),
        created_at=_parse_dt_required(row.created_at),
        updated_at=_parse_dt_required(row.updated_at),
    )


def repo_row_to_out(row: RepoRow) -> RepoOut:
    return RepoOut(
        id=row.id,
        owner=row.owner,
        name=row.name,
        description=row.description or "",
        default_branch=row.default_branch,
        enabled=bool(row.enabled),
        last_sync_at=_parse_dt(row.last_sync_at),
        created_at=_parse_dt_required(row.created_at),
        updated_at=_parse_dt_required(row.updated_at),
    )


def backup_row_to_out(row: BackupRow, *, host_name: str) -> BackupOut:
    return BackupOut(
        id=row.id,
        name=row.name,
        host_id=row.host_id,
        host_name=host_name,
        backup_type=row.backup_type,
        command=row.command,
        target_path=row.target_path,
        schedule_cron=row.schedule_cron,
        enabled=bool(row.enabled),
        last_run_at=_parse_dt(row.last_run_at),
        last_run_status=row.last_run_status,
        last_size_bytes=row.last_size_bytes,
        created_at=_parse_dt_required(row.created_at),
        updated_at=_parse_dt_required(row.updated_at),
    )


def secret_row_to_out(row: SecretRow) -> SecretOut:
    return SecretOut(
        id=row.id,
        key=row.key,
        app_tag=row.app_tag,
        host_tag=row.host_tag,
        comment=row.comment or "",
        last_used_at=_parse_dt(row.last_used_at),
        last_used_purpose=row.last_used_purpose,
        reveal_count=row.reveal_count or 0,
        created_at=_parse_dt_required(row.created_at),
        updated_at=_parse_dt_required(row.updated_at),
    )


def traffic_source_row_to_out(row: TrafficSourceRow, *, host_name: str) -> TrafficSourceOut:
    return TrafficSourceOut(
        id=row.id,
        host_id=row.host_id,
        host_name=host_name,
        log_path=row.log_path,
        log_format=row.log_format,
        server_app_map=_decode_json_list(row.server_app_map, []),
        last_collect_at=_parse_dt(row.last_collect_at),
        last_status=row.last_status,
        last_error=row.last_error,
        enabled=bool(row.enabled),
        created_at=_parse_dt_required(row.created_at),
        updated_at=_parse_dt_required(row.updated_at),
    )


def deployment_row_to_out(row: DeploymentRow, *, app_name: str) -> DeploymentOut:
    return DeploymentOut(
        id=row.id,
        app_id=row.app_id,
        app_name=app_name,
        ts=_parse_dt_required(row.ts),
        image=row.image,
        image_digest=row.image_digest,
        git_sha=row.git_sha,
        source=row.source,
        actor=row.actor,
        status=row.status,
        notes=row.notes,
        duration_s=row.duration_s,
        created_at=_parse_dt_required(row.created_at),
    )


def audit_row_to_out(row: AuditRow) -> AuditOut:
    return AuditOut(
        id=row.id,
        ts=_parse_dt_required(row.ts),
        actor=row.actor,
        action=row.action,
        target=row.target,
        before=_decode_json(row.before),
        after=_decode_json(row.after),
        ip=row.ip,
        notes=row.notes,
    )
