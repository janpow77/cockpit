"""Aufträge (Kanban): anlegen, planen, starten, stoppen, nachfragen, Protokoll lesen.

  GET    /admin/api/auftraege              Liste + Kapazität
  POST   /admin/api/auftraege              anlegen
  GET    /admin/api/auftraege/projekte     Projektverzeichnisse je Host (aus der Werkstatt)
  GET    /admin/api/auftraege/vorlagen     vorformulierte Aufträge
  PATCH  /admin/api/auftraege/{id}         Felder/Status/Reihenfolge ändern
  POST   /admin/api/auftraege/{id}/start   sofort starten (wenn Kapazität)
  POST   /admin/api/auftraege/{id}/stop    laufenden Auftrag beenden
  POST   /admin/api/auftraege/{id}/nachfrage  Folgeauftrag in derselben Sitzung (--resume)
  GET    /admin/api/auftraege/{id}/log     lesbares Protokoll des Laufs
  DELETE /admin/api/auftraege/{id}
"""

from __future__ import annotations

import asyncio
import logging
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..auth import require_auth
from ..crud import audit as crud_audit
from ..db import get_session
from ..services import auftraege as svc
from ..services import auftrag_runner as runner
from ..services import auftrag_vorlagen
from ..services import wall_config as wc
from ..services.ssh_runner import run_on_host

log = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/api/auftraege", tags=["auftraege"])

Profil = Literal["lesen", "bearbeiten", "bearbeiten_tests", "voll"]
Zeitfenster = Literal["sofort", "nachts", "nach_reset"]
Agent = Literal["claude", "codex", "gemini"]


class AuftragNeu(BaseModel):
    titel: str = Field(min_length=3, max_length=160)
    text: str = Field(min_length=10, max_length=12000)
    host: str = Field(min_length=1, max_length=64)
    projekt: str = Field(min_length=2, max_length=400)
    agent: Agent = "claude"
    profil: Profil = "bearbeiten"
    prioritaet: int = Field(default=3, ge=1, le=5)
    zeitfenster: Zeitfenster = "sofort"
    status: Literal["eingang", "geplant"] = "eingang"


class AuftragPatch(BaseModel):
    status: Literal["eingang", "geplant", "fertig", "rueckfrage"] | None = None
    prioritaet: int | None = Field(default=None, ge=1, le=5)
    reihenfolge: int | None = None
    titel: str | None = Field(default=None, min_length=3, max_length=160)
    text: str | None = Field(default=None, min_length=10, max_length=12000)
    profil: Profil | None = None
    zeitfenster: Zeitfenster | None = None
    agent: Agent | None = None


class Nachfrage(BaseModel):
    text: str = Field(min_length=2, max_length=6000)


def _projekt_name(pfad: str) -> str:
    return pfad.rstrip("/").rsplit("/", 1)[-1]


@router.get("")
async def liste(_=Depends(require_auth), session: Session = Depends(get_session)) -> dict:
    rows = svc.liste(session)
    return {"auftraege": [svc.as_dict(a) for a in rows], "kapazitaet": runner.kapazitaet(session)}


@router.get("/projekte")
async def projekte(_=Depends(require_auth), session: Session = Depends(get_session)) -> list[dict]:
    """Projektverzeichnisse: alle Repos aus der Werkstatt des letzten Wand-Standes, sonst die work_dirs."""
    from ..services import wall_loop

    cfg = wc.load(session)
    stand = wall_loop.letzter_stand() or {}
    out: list[dict] = []
    gesehen: set[tuple[str, str]] = set()
    for w in stand.get("werkstatt") or []:
        basis = cfg.work_dirs.get(w.get("host") or "")
        if not basis:
            continue
        for r in w.get("repos") or []:
            pfad = f"{basis.rstrip('/')}/{r.get('name')}"
            key = (w["host"], pfad)
            if key in gesehen:
                continue
            gesehen.add(key)
            out.append({"host": w["host"], "pfad": pfad, "name": r.get("name"), "aktiv": bool(r.get("aktiv"))})
    if not out:
        for host, basis in cfg.work_dirs.items():
            out.append({"host": host, "pfad": basis, "name": _projekt_name(basis), "aktiv": True})
    out.sort(key=lambda p: (not p.get("aktiv"), p["host"], p["name"].lower()))
    return out


@router.get("/vorlagen")
async def vorlagen(_=Depends(require_auth), session: Session = Depends(get_session)) -> list[dict]:
    cfg = wc.load(session)
    return auftrag_vorlagen.vorlagen(cfg.auftrag_vorlagen)


class VorschlaegeAnfrage(BaseModel):
    host: str = Field(min_length=1, max_length=64)
    projekt: str = Field(min_length=2, max_length=400)
    agent: Agent = "claude"


@router.post("/vorschlaege", status_code=201)
async def vorschlaege_einholen(req: VorschlaegeAnfrage, _=Depends(require_auth), session: Session = Depends(get_session)) -> dict:
    """Vorschlags-Lauf für ein Projekt anlegen (geplant, sofort): Ergebnis landet als Karten im Eingang."""
    cfg = wc.load(session)
    vorlage = next((x for x in auftrag_vorlagen.vorlagen(cfg.auftrag_vorlagen) if x["id"] == "vorschlaege"), None)
    if vorlage is None:
        raise HTTPException(status_code=404, detail="Vorlage »vorschlaege« fehlt")
    name = _projekt_name(req.projekt)
    a = svc.anlegen(session, titel=vorlage["titel"].replace("{projekt}", name), text=vorlage["text"], host=req.host, projekt=req.projekt.rstrip("/"),
                    projekt_name=name, agent=req.agent, profil="lesen", prioritaet=2, zeitfenster="sofort", status="geplant")
    crud_audit.write(session, action="auftrag.vorschlaege", target=a.id, after={"projekt": a.projekt, "agent": a.agent})
    return svc.as_dict(a)


@router.post("", status_code=201)
async def anlegen(req: AuftragNeu, _=Depends(require_auth), session: Session = Depends(get_session)) -> dict:
    a = svc.anlegen(
        session, titel=req.titel.strip(), text=req.text.strip(), host=req.host, projekt=req.projekt.rstrip("/"),
        projekt_name=_projekt_name(req.projekt), agent=req.agent, profil=req.profil, prioritaet=req.prioritaet,
        zeitfenster=req.zeitfenster, status=req.status,
    )
    crud_audit.write(session, action="auftrag.anlegen", target=a.id, after={"titel": a.titel, "projekt": a.projekt, "profil": a.profil})
    return svc.as_dict(a)


@router.patch("/{auftrag_id}")
async def aendern(auftrag_id: str, req: AuftragPatch, _=Depends(require_auth), session: Session = Depends(get_session)) -> dict:
    a = svc.holen(session, auftrag_id)
    if a is None:
        raise HTTPException(status_code=404, detail="Auftrag nicht gefunden")
    felder = {k: v for k, v in req.model_dump().items() if v is not None}
    if "status" in felder:
        if a.status == "laeuft":
            raise HTTPException(status_code=409, detail="Laufender Auftrag – zuerst stoppen")
        if felder["status"] in ("eingang", "geplant") and a.status in ("fertig", "fehler", "abgebrochen", "rueckfrage"):
            felder.update({"beendet": None, "fehler": None})
    if "text" in felder:
        felder["text"] = felder["text"].strip()
    a = svc.aendern(session, a, **felder)
    return svc.as_dict(a)


@router.post("/{auftrag_id}/start")
async def starten(auftrag_id: str, _=Depends(require_auth), session: Session = Depends(get_session)) -> dict:
    a = svc.holen(session, auftrag_id)
    if a is None:
        raise HTTPException(status_code=404, detail="Auftrag nicht gefunden")
    if a.status == "laeuft":
        raise HTTPException(status_code=409, detail="Läuft bereits")
    kap = runner.kapazitaet(session)
    if kap["laufend"] >= kap["parallel_max"]:
        a = svc.aendern(session, a, status="geplant")
        raise HTTPException(status_code=409, detail=kap.get("pause_grund") or f"Kapazität erschöpft ({kap['laufend']}/{kap['parallel_max']}) – geplant, startet automatisch")
    cfg = wc.load(session)
    a = await asyncio.to_thread(svc.starten, session, a, bins=dict(cfg.agent_bins))
    crud_audit.write(session, action="auftrag.start", target=a.id, after={"status": a.status, "fehler": a.fehler})
    return svc.as_dict(a)


@router.post("/{auftrag_id}/stop")
async def stoppen(auftrag_id: str, _=Depends(require_auth), session: Session = Depends(get_session)) -> dict:
    a = svc.holen(session, auftrag_id)
    if a is None:
        raise HTTPException(status_code=404, detail="Auftrag nicht gefunden")
    if a.status != "laeuft":
        raise HTTPException(status_code=409, detail="Auftrag läuft nicht")
    a = await asyncio.to_thread(svc.stoppen, session, a)
    crud_audit.write(session, action="auftrag.stop", target=a.id)
    return svc.as_dict(a)


@router.post("/{auftrag_id}/nachfrage")
async def nachfrage(auftrag_id: str, req: Nachfrage, _=Depends(require_auth), session: Session = Depends(get_session)) -> dict:
    a = svc.holen(session, auftrag_id)
    if a is None:
        raise HTTPException(status_code=404, detail="Auftrag nicht gefunden")
    if a.status == "laeuft":
        raise HTTPException(status_code=409, detail="Läuft gerade – Nachfrage erst nach Ende")
    if not a.session_id:
        raise HTTPException(status_code=409, detail="Keine Sitzung zum Fortsetzen (noch nie gelaufen)")
    cfg = wc.load(session)
    text = req.text.strip()
    a = svc.aendern(session, a, text=f"{a.text}\n\n--- Nachfrage ---\n{text}")
    a = await asyncio.to_thread(svc.starten, session, a, bins=dict(cfg.agent_bins), resume=True, nachfrage=text)
    crud_audit.write(session, action="auftrag.nachfrage", target=a.id, after={"text": text[:300]})
    return svc.as_dict(a)


@router.get("/{auftrag_id}/log")
async def protokoll(auftrag_id: str, zeilen: int = 80, _=Depends(require_auth), session: Session = Depends(get_session)) -> dict:
    a = svc.holen(session, auftrag_id)
    if a is None:
        raise HTTPException(status_code=404, detail="Auftrag nicht gefunden")
    if not a.gestartet:
        return {"zeilen": []}
    host = svc.host_fuer(session, a.host)
    if host is None:
        return {"zeilen": [{"ts": None, "art": "fehler", "text": f"Host {a.host} nicht erreichbar"}]}
    zeilen = max(10, min(400, zeilen))
    try:
        res = await asyncio.to_thread(run_on_host, host, svc.stand_befehl(a, zeilen * 3), timeout=25)
    except Exception as exc:  # noqa: BLE001
        return {"zeilen": [{"ts": None, "art": "fehler", "text": str(exc)[:200]}]}
    roh = res.stdout or ""
    out = svc.log_zeilen(roh, max_zeilen=zeilen, agent=a.agent)
    stderr_teil = roh.split("---STDERR---", 1)[1].strip() if "---STDERR---" in roh else ""
    if stderr_teil and a.status in ("fehler", "laeuft"):
        out.append({"ts": None, "art": "fehler", "text": stderr_teil[-600:]})
    return {"zeilen": out}


@router.delete("/{auftrag_id}", status_code=204)
async def loeschen(auftrag_id: str, _=Depends(require_auth), session: Session = Depends(get_session)) -> None:
    a = svc.holen(session, auftrag_id)
    if a is None:
        raise HTTPException(status_code=404, detail="Auftrag nicht gefunden")
    if a.status == "laeuft":
        raise HTTPException(status_code=409, detail="Laufender Auftrag – zuerst stoppen")
    session.delete(a)
    session.commit()
    crud_audit.write(session, action="auftrag.loeschen", target=auftrag_id)
