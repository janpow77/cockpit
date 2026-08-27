"""MCP-Einstellungen: Server der Landschaft, Werkzeuge, Skills, Konfigurationsvorlage.

  GET /admin/api/mcp/servers   alle konfigurierten MCP-Server mit Live-Zustand

Server-Liste liegt in der Wand-Konfiguration (`wall.mcp_servers`). HTTP-Server
werden per JSON-RPC befragt (initialize, tools/list, skills_list); stdio-Server
lassen sich nur beschreiben und ueber eine Health-URL pruefen. Secrets kommen
aus dem Vault und werden nie ausgeliefert - der Nutzer sieht Platzhalter.
"""

from __future__ import annotations

import asyncio
import logging

import httpx
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..auth import require_auth
from ..db import get_session
from ..services import mcp_client
from ..services import wall_config as wc
from .overview import _secret_value

log = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/api/mcp", tags=["mcp"])


async def _health(url: str | None, headers: dict[str, str]) -> dict:
    if not url:
        return {"ok": None, "note": "keine Health-URL"}
    try:
        async with httpx.AsyncClient(timeout=8.0) as c:
            resp = await c.get(url, headers=headers)
        return {"ok": resp.status_code < 400, "note": f"HTTP {resp.status_code}"}
    except httpx.HTTPError as exc:
        return {"ok": False, "note": str(exc)[:120]}


async def _inspect_server(session: Session, srv: dict) -> dict:
    headers: dict[str, str] = {}
    secret_ok = None
    if srv.get("secret_key"):
        value = _secret_value(session, srv["secret_key"])
        secret_ok = bool(value)
        if value:
            headers[srv.get("header") or "Authorization"] = f"{srv.get('header_prefix', '')}{value}"
    out = {
        "id": srv.get("id"),
        "name": srv.get("name") or srv.get("id"),
        "transport": srv.get("transport", "http"),
        "url": srv.get("url"),
        "command": srv.get("command"),
        "description": srv.get("description", ""),
        "secret_key": srv.get("secret_key"),
        "secret_ok": secret_ok,
        "header": srv.get("header"),
        "snippet": mcp_client.claude_code_snippet(
            srv.get("id", "server"), srv.get("url") or "", srv.get("header"), srv.get("header_prefix", "")
        ) if srv.get("transport", "http") == "http" else (srv.get("snippet") or ""),
        "health": None,
        "inspect": None,
    }
    if srv.get("health_url"):
        out["health"] = await _health(srv["health_url"], headers if srv.get("health_with_secret") else {})
    if srv.get("transport", "http") == "http" and srv.get("url"):
        client = mcp_client.McpHttp(srv["url"], headers)
        out["inspect"] = await asyncio.to_thread(client.inspect, skills_tool=srv.get("skills_tool", "skills_list"))
    return out


@router.get("/servers")
async def servers(_=Depends(require_auth), session: Session = Depends(get_session)) -> dict:
    cfg = wc.load(session)
    ergebnisse = await asyncio.gather(*(_inspect_server(session, s) for s in cfg.mcp_servers), return_exceptions=True)
    out = []
    for srv, res in zip(cfg.mcp_servers, ergebnisse, strict=False):
        if isinstance(res, BaseException):
            log.warning("MCP-Server %s: %s", srv.get("id"), res)
            out.append({"id": srv.get("id"), "name": srv.get("name"), "error": str(res)[:160]})
        else:
            out.append(res)
    return {"servers": out}
