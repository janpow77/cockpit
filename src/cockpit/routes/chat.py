"""KI-Konsole: Chat mit einem lokalen Modell ueber den ai-router (Streaming).

  GET  /admin/api/chat/models  freigegebene Modelle (Whitelist ∩ Router)
  POST /admin/api/chat         Server-Sent Events: {delta} ... {done}

Kein Verlauf wird gespeichert; jeder Aufruf traegt den Gespraechsverlauf
selbst. Systemprompt und Modell-Whitelist stehen in der Wand-Konfiguration.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
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


class MerkenRequest(BaseModel):
    content: str = Field(min_length=10, max_length=6000)
    category: Literal["problem", "solution", "preference", "architecture", "workflow", "reference", "feedback", "pattern"] = "solution"
    project: str | None = Field(default=None, max_length=100)
    tags: list[str] | None = None


# Bei "Beides" lohnt die Wissensbasis (EFRE-Recht, Verordnungen) nur bei fachlichen Fragen -
# sonst kostet sie 5-10 s und liefert Beifang.
_FACHLICH = re.compile(
    r"\b(Art\.|Artikel|§|Verordnung|VO\b|CPR|EFRE|ESF|Prüfbehörde|Verwaltungsbehörde|Förder|Zuwendung|Vorhaben|"
    r"Checkliste|Feststellung|TER\b|RER\b|Rechnungslegung|Jahresbericht|Systemprüfung|Kernanforderung|Gesetz|"
    r"Richtlinie|Leitfaden|OWiG|KPAnG|Bußgeld|Kartell|Vergabe|Beihilfe|Haushaltsordnung|Kommission)",
    re.I,
)


def rag_modus_effektiv(modus: str, frage: str) -> str:
    """'both' nur mit Wissensbasis, wenn die Frage fachlich klingt (rein, testbar)."""
    if modus == "both" and not _FACHLICH.search(frage or ""):
        return "memory"
    return modus


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
    available = await asyncio.to_thread(ai_router_client.list_models)
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
    erlaubt = {m["tag"] for m in allowed_models(cfg, await asyncio.to_thread(ai_router_client.list_models))}
    if req.model not in erlaubt:
        raise HTTPException(status_code=422, detail=f"Modell „{req.model}“ ist nicht freigegeben oder nicht geladen.")

    # Kira-RAG: die letzte Nutzerfrage wird gesucht, Treffer wandern als Kontext in den Systemprompt
    quellen: list[dict] = []
    rag_note: str | None = None
    t0 = time.monotonic()
    if req.rag != "off":
        # Suchanfrage: die letzte Nutzerfrage, bei Rueckfragen ("und wie ...") plus die davor
        nutzer = [m.content for m in req.messages if m.role == "user"]
        frage = nutzer[-1] if nutzer else ""
        if len(nutzer) > 1 and len(frage) < 80:
            frage = f"{nutzer[-2]} {frage}"
        mcp_server, mcp_headers = _mcp_zugang(session, cfg)
        kira_host = next((h for h in crud_hosts.list_hosts(session) if h.name == str(cfg.kira.get("host") or "")), None)
        quellen, rag_note = await rag.suchen(
            query=frage, modus=rag_modus_effektiv(req.rag, frage), project=(req.rag_project or "").strip() or None,
            mcp_server=mcp_server, mcp_headers=mcp_headers, kira_host=kira_host, kira_cfg=cfg.kira, hide=cfg.hide,
        )

    log.info(
        "Konsole: modell=%s rag=%s projekt=%s quellen=%d (gedaechtnis %d, wissen %d) suche=%d ms hinweis=%s",
        req.model, req.rag, req.rag_project or "-", len(quellen),
        sum(1 for q in quellen if q["quelle"] == "memory"), sum(1 for q in quellen if q["quelle"] == "knowledge"),
        int((time.monotonic() - t0) * 1000), rag_note or "-",
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
    options["num_predict"] = int(cfg.chat_max_tokens)

    async def sse():
        if req.rag != "off":
            yield f"data: {json.dumps({'sources': quellen, 'rag_note': rag_note}, ensure_ascii=False)}\n\n"
        async for chunk in ai_router_client.chat_stream(
            req.model, messages, options=options or None, think=bool(cfg.chat_think)
        ):
            yield f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n"
            if chunk.get("done") or chunk.get("error"):
                break

    return StreamingResponse(
        sse(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/merken")
async def merken(
    req: MerkenRequest, _=Depends(require_auth), session: Session = Depends(get_session)
) -> dict:
    """Antwort/Entscheidung ins Kira-Gedächtnis schreiben: memory_add über MCP, sonst Memory-API auf dem Kira-Host."""
    cfg = wc.load(session)
    tags = [t.strip()[:40] for t in (req.tags or []) if t.strip()][:10]
    if "cockpit-konsole" not in tags:
        tags.append("cockpit-konsole")
    project = (req.project or "").strip() or None
    mcp_server, mcp_headers = _mcp_zugang(session, cfg)
    if mcp_server and mcp_headers:
        try:
            args = {"content": req.content, "category": req.category, "tags": tags}
            if project:
                args["project"] = project
            obj = await asyncio.to_thread(rag._mcp_tool, mcp_server["url"], mcp_headers, "memory_add", args)
            if isinstance(obj, dict) and (obj.get("id") or obj.get("entry_id")):
                return {"ok": True, "id": obj.get("id") or obj.get("entry_id"), "weg": "mcp", "hinweis": None}
            log.warning("memory_add über MCP ohne ID: %s", str(obj)[:160])
        except Exception as exc:  # noqa: BLE001 - Rueckfall folgt
            log.warning("memory_add über MCP: %s", exc)
    kira_host = next((h for h in crud_hosts.list_hosts(session) if h.name == str(cfg.kira.get("host") or "")), None)
    if kira_host is None:
        raise HTTPException(status_code=502, detail="Gedächtnis nicht erreichbar (kein MCP-Token, kein Kira-Host)")
    body = {"content": req.content, "category": req.category, "tags": tags}
    if project:
        body["project"] = project
    obj = await asyncio.to_thread(rag._memory_api_schreiben, kira_host, cfg.kira, body)
    if isinstance(obj, dict) and obj.get("id"):
        return {"ok": True, "id": obj["id"], "weg": "api", "hinweis": None}
    raise HTTPException(status_code=502, detail=f"Gedächtnis hat nicht gespeichert: {str(obj)[:160]}")
