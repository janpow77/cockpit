"""KI-Konsole: Chat mit einem lokalen Modell ueber den ai-router (Streaming).

  GET  /admin/api/chat/models  freigegebene Modelle (Whitelist ∩ Router)
  POST /admin/api/chat         Server-Sent Events: {delta} ... {done}

Kein Verlauf wird gespeichert; jeder Aufruf traegt den Gespraechsverlauf
selbst. Systemprompt und Modell-Whitelist stehen in der Wand-Konfiguration.
"""

from __future__ import annotations

import json
import logging
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..auth import require_auth
from ..crud import hosts as crud_hosts
from ..db import get_session
from ..services import ai_router_client, rag
from ..services import wall_config as wc
from .overview import _secret_value

log = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/api/chat", tags=["chat"])

MAX_MESSAGES = 40
MAX_CHARS = 24_000


class ChatMessage(BaseModel):
    role: Literal["user", "assistant", "system"]
    content: str = Field(min_length=1, max_length=MAX_CHARS)


class ChatRequest(BaseModel):
    model: str = Field(min_length=1, max_length=200)
    messages: list[ChatMessage] = Field(min_length=1, max_length=MAX_MESSAGES)
    system: str | None = Field(default=None, max_length=4000)
    temperature: float | None = Field(default=None, ge=0.0, le=2.0)
    # Kira-RAG: 'memory' = Projektgedaechtnis, 'knowledge' = Wissensbasis, 'both', 'off'
    rag: Literal["off", "memory", "knowledge", "both"] = "off"
    rag_project: str | None = Field(default=None, max_length=100)


def _mcp_zugang(session: Session, cfg: wc.WallConfig) -> tuple[dict | None, dict[str, str]]:
    """Erster HTTP-MCP-Server mit Vault-Secret (Vorgabe: flowaudit) + fertige Header."""
    for srv in cfg.mcp_servers:
        if srv.get("transport", "http") != "http" or not srv.get("url"):
            continue
        value = _secret_value(session, srv.get("secret_key"))
        if not value:
            continue
        return srv, {srv.get("header") or "Authorization": f"{srv.get('header_prefix', '')}{value}"}
    return None, {}


def allowed_models(cfg: wc.WallConfig, available: list[dict]) -> list[dict]:
    """Whitelist ∩ tatsaechlich geladene Modelle, mit Anzeigenamen (rein, testbar)."""
    by_name = {m["name"]: m for m in available}
    out: list[dict] = []
    for entry in cfg.chat_models:
        tag = entry.get("tag", "")
        if tag in by_name:
            m = by_name[tag]
            out.append({
                "tag": tag,
                "label": entry.get("label") or tag,
                "parameter_size": m.get("parameter_size", ""),
                "size_bytes": m.get("size_bytes", 0),
            })
    return out


@router.get("/models")
async def list_models(_=Depends(require_auth), session: Session = Depends(get_session)) -> dict:
    cfg = wc.load(session)
    available = ai_router_client.list_models()
    return {
        "router": ai_router_client.base_url(),
        "router_ok": bool(available),
        "models": allowed_models(cfg, available),
        "system": cfg.chat_system,
    }


@router.post("")
async def chat(
    req: ChatRequest, _=Depends(require_auth), session: Session = Depends(get_session)
) -> StreamingResponse:
    cfg = wc.load(session)
    erlaubt = {m["tag"] for m in allowed_models(cfg, ai_router_client.list_models())}
    if req.model not in erlaubt:
        raise HTTPException(status_code=422, detail=f"Modell „{req.model}“ ist nicht freigegeben oder nicht geladen.")

    # Kira-RAG: die letzte Nutzerfrage wird gesucht, Treffer wandern als Kontext in den Systemprompt
    quellen: list[dict] = []
    rag_note: str | None = None
    if req.rag != "off":
        frage = next((m.content for m in reversed(req.messages) if m.role == "user"), "")
        mcp_server, mcp_headers = _mcp_zugang(session, cfg)
        kira_host = next((h for h in crud_hosts.list_hosts(session) if h.name == str(cfg.kira.get("host") or "")), None)
        quellen, rag_note = await rag.suchen(
            query=frage, modus=req.rag, project=(req.rag_project or "").strip() or None,
            mcp_server=mcp_server, mcp_headers=mcp_headers, kira_host=kira_host, kira_cfg=cfg.kira, hide=cfg.hide,
        )

    messages: list[dict] = []
    system = (req.system or cfg.chat_system or "").strip()
    kontext = rag.kontext_block(quellen)
    if kontext:
        system = f"{system}\n\n{kontext}" if system else kontext
    if system:
        messages.append({"role": "system", "content": system})
    messages.extend({"role": m.role, "content": m.content} for m in req.messages if m.role != "system")
    options: dict = {}
    if req.temperature is not None:
        options["temperature"] = req.temperature
    if kontext:
        options["num_ctx"] = int(cfg.chat_num_ctx)

    async def sse():
        if req.rag != "off":
            yield f"data: {json.dumps({'sources': quellen, 'rag_note': rag_note}, ensure_ascii=False)}\n\n"
        async for chunk in ai_router_client.chat_stream(req.model, messages, options=options or None):
            yield f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n"
            if chunk.get("done") or chunk.get("error"):
                break

    return StreamingResponse(
        sse(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
