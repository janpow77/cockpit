"""FastAPI-App fuer Cockpit.

- Mounted alle 7 Routes-Module unter /admin/api/*
- Initialisiert die DB beim Startup, spielt Migrationen + Bootstrap ein
- Startet die Health-Loop als Background-Task
- Bedient die Vue-3-SPA aus /app/frontend_dist unter /admin/
"""
from __future__ import annotations

import asyncio
import logging
import os
import time
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from . import __version__
from .config import load_config
from .db import get_session_factory, init_db
from .routes.apps import router as apps_router
from .routes.audit import router as audit_router
from .routes.auth import router as auth_router
from .routes.backups import router as backups_router
from .routes.chat import router as chat_router
from .routes.dashboard import router as dashboard_router
from .routes.deployments import router as deployments_router
from .routes.github import router as github_router
from .routes.hosts import router as hosts_router
from .routes.mcp import router as mcp_router
from .routes.overview import router as overview_router
from .routes.secrets import router as secrets_router
from .routes.settings import router as settings_router
from .routes.traffic import router as traffic_router
from .services import bootstrap, health_check, traffic_collector

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)s  %(name)s  %(message)s",
)
log = logging.getLogger("cockpit")


_APP_STATE: dict = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    cfg = load_config()
    log.info("Cockpit %s startet — db=%s vault=%s github=%s", __version__,
             cfg.db_path, "on" if cfg.vault_key else "off",
             "on" if cfg.github_token else "off")
    init_db()
    _APP_STATE["started_at"] = time.time()
    _APP_STATE["stop_event"] = asyncio.Event()

    # Bootstrap: Default-Hosts + Default-Apps
    try:
        with get_session_factory()() as session:
            n_hosts = bootstrap.bootstrap_hosts(session, cfg)
            n_apps = bootstrap.bootstrap_apps(session)
            if n_hosts:
                log.info("Bootstrap: %d Default-Host(s) angelegt.", n_hosts)
            if n_apps:
                log.info("Bootstrap: %d Default-App(s) angelegt.", n_apps)
    except Exception as exc:  # noqa: BLE001
        log.warning("Bootstrap fehlgeschlagen: %s", exc)

    # Background-Tasks
    interval = 60
    try:
        with get_session_factory()() as session:
            from .models import SettingRow
            row = session.get(SettingRow, "health_interval_s")
            if row:
                import json
                interval = int(json.loads(row.value))
    except Exception:
        pass

    health_task = asyncio.create_task(
        health_check.health_loop(_APP_STATE["stop_event"], interval_s=interval)
    )
    _APP_STATE["health_task"] = health_task

    # Traffic-Collector: 60-Sekunden-Pull. Default an, deaktivierbar
    # ueber COCKPIT_TRAFFIC_COLLECT=off (z.B. fuer Tests).
    traffic_interval = int(os.environ.get("COCKPIT_TRAFFIC_INTERVAL_S", "60"))
    traffic_task: asyncio.Task | None = None
    if os.environ.get("COCKPIT_TRAFFIC_COLLECT", "on").lower() not in ("off", "false", "0"):
        traffic_task = asyncio.create_task(
            traffic_collector.traffic_loop(_APP_STATE["stop_event"], interval_s=traffic_interval),
        )
        _APP_STATE["traffic_task"] = traffic_task

    try:
        yield
    finally:
        _APP_STATE["stop_event"].set()
        for name, task in [("health_task", health_task), ("traffic_task", traffic_task)]:
            if task is None:
                continue
            try:
                await asyncio.wait_for(task, timeout=5.0)
            except (TimeoutError, asyncio.CancelledError):
                task.cancel()
            except Exception as exc:
                log.warning("%s Shutdown: %s", name, exc)
        log.info("Cockpit stoppt.")


app = FastAPI(
    title="cockpit",
    version=__version__,
    description="Multi-App-Multi-Host-Verwaltungs-Hub",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/admin/api/health")
async def health() -> dict:
    started = _APP_STATE.get("started_at") or time.time()
    return {
        "status": "ok",
        "version": __version__,
        "started_at": datetime.fromtimestamp(started, tz=UTC).isoformat().replace("+00:00", "Z"),
        "uptime_s": int(time.time() - started),
    }


@app.get("/health")
async def health_root() -> dict:
    return await health()


@app.get("/", include_in_schema=False)
async def root_redirect() -> RedirectResponse:
    return RedirectResponse(url="/admin/")


@app.exception_handler(Exception)
async def unhandled_exception(_request, exc: Exception):
    log.exception("Unhandled: %s", exc)
    return JSONResponse(status_code=500, content={"error": "internal", "detail": str(exc)[:200]})


app.include_router(auth_router)
app.include_router(dashboard_router)
app.include_router(hosts_router)
app.include_router(apps_router)
app.include_router(github_router)
app.include_router(backups_router)
app.include_router(secrets_router)
app.include_router(audit_router)
app.include_router(settings_router)
app.include_router(traffic_router)
app.include_router(deployments_router)
app.include_router(overview_router)
app.include_router(chat_router)
app.include_router(mcp_router)


# ---------------------------- SPA ----------------------------------------
# Vue 3 SPA wird im Docker-Build nach /app/frontend_dist gelegt.

_FRONTEND_DIR = Path(__file__).resolve().parent.parent.parent / "frontend_dist"


def _mount_spa() -> None:
    if not (_FRONTEND_DIR / "index.html").exists():
        log.warning("Admin-Frontend nicht gefunden unter %s — UI nicht verfuegbar", _FRONTEND_DIR)
        return

    if (_FRONTEND_DIR / "assets").exists():
        app.mount(
            "/admin/assets",
            StaticFiles(directory=_FRONTEND_DIR / "assets"),
            name="cockpit-assets",
        )

    @app.get("/admin", include_in_schema=False)
    @app.get("/admin/", include_in_schema=False)
    async def _admin_root():
        return FileResponse(_FRONTEND_DIR / "index.html")

    @app.get("/admin/{full_path:path}", include_in_schema=False)
    async def _admin_spa(full_path: str):
        if full_path.startswith("api/"):
            # Sollte vom APIRouter abgefangen werden — schuetzt vor Catch-All-Bug
            return JSONResponse(status_code=404, content={"detail": "Not Found"})
        candidate = _FRONTEND_DIR / full_path
        if candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(_FRONTEND_DIR / "index.html")


_mount_spa()
