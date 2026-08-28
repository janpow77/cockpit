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
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth import require_auth
from ..crud import audit as crud_audit
from ..db import get_session
from ..models import HostRow
from ..services import auftraege as svc
from ..services import auftrag_runner as runner
from ..services import auftrag_vorlagen
from ..services import flow_agent as fa
from ..services import wall_config as wc
from ..services.ssh_runner import run_on_host

log = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/api/auftraege", tags=["auftraege"])

Profil = Literal["lesen", "bearbeiten", "bearbeiten_tests", "voll"]
Zeitfenster = Literal["sofort", "nachts", "nach_reset"]
Agent = Literal["claude", "codex", "gemini"]
Modus = Literal["bericht", "plan_freigabe", "umsetzen"]


class AuftragNeu(BaseModel):
    titel: str = Field(min_length=3, max_length=160)
    text: str = Field(min_length=10, max_length=12000)
    host: str = Field(min_length=1, max_length=64)
    projekt: str = Field(min_length=2, max_length=400)
    agent: Agent = "claude"
    modus: Modus = "plan_freigabe"
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
    modus: Modus | None = None


class Nachfrage(BaseModel):
    text: str = Field(min_length=2, max_length=6000)


class Freigabe(BaseModel):
    hinweis: str | None = Field(default=None, max_length=4000)


class RunnerSchalter(BaseModel):
    angehalten: bool


class Aufraeumen(BaseModel):
    branch_loeschen: bool = False


def _projekt_name(pfad: str) -> str:
    return pfad.rstrip("/").rsplit("/", 1)[-1]


@router.get("")
async def liste(_=Depends(require_auth), session: Session = Depends(get_session)) -> dict:
    rows = svc.liste(session)
    return {"auftraege": [svc.as_dict(a) for a in rows], "kapazitaet": runner.kapazitaet(session)}


def _flow_agent_zugang(session: Session, cfg: wc.WallConfig) -> tuple[str, str | None, dict[str, str]]:
    from .overview import _secret_value

    f = cfg.flow_agent or {}
    url = str(f.get("url") or "https://agent.flowaudit.de")
    token = _secret_value(session, str(f.get("secret_key") or "flow_agent_read_key"))
    hosts = f.get("hosts") if isinstance(f.get("hosts"), dict) else {}
    return url, token, {str(k): str(x) for k, x in hosts.items()}


def _flow_agent_projekt(session: Session, cfg: wc.WallConfig, host: str, pfad: str) -> tuple[dict | None, dict | None]:
    """Projektzeile und graphify-Stand aus flow-agent für einen Auftrag (None, wenn unbekannt oder kein Zugang)."""
    url, token, hosts = _flow_agent_zugang(session, cfg)
    if not token:
        return None, None
    name = _projekt_name(pfad)
    p = next((x for x in fa.projekte(url, token, hosts) if x["host"] == host and (x["pfad"] == pfad.rstrip("/") or x["name"] == name)), None)
    g = fa.graphify(url, token, hosts).get((host, name))
    return p, g


@router.get("/projekte")
async def projekte(_=Depends(require_auth), session: Session = Depends(get_session)) -> list[dict]:
    """Projektverzeichnisse: Werkstatt des letzten Wand-Standes plus Inventar von flow-agent (alle Hosts), sonst die work_dirs."""
    from ..services import wall_loop

    cfg = wc.load(session)
    stand = wall_loop.letzter_stand() or {}
    out: list[dict] = []
    gesehen: set[tuple[str, str]] = set()
    url, token, hosts = _flow_agent_zugang(session, cfg)
    bekannte_hosts = {h.name for h in session.execute(select(HostRow)).scalars()}
    agent_hosts = set(cfg.agent_hosts)

    def grund(host: str) -> str | None:
        if host not in bekannte_hosts:
            return "kein SSH-Zugang"
        if host not in agent_hosts:
            return "keine Agenten auf diesem Host"
        return None
    if token:
        graph = fa.graphify(url, token, hosts)
        for p in fa.projekte(url, token, hosts):
            key = (p["host"], p["pfad"])
            if key in gesehen or not p.get("git"):
                continue
            gesehen.add(key)
            g = graph.get((p["host"], p["name"])) or {}
            out.append({
                "host": p["host"], "pfad": p["pfad"], "name": p["name"], "aktiv": p.get("status") in ("healthy", "ok", "degraded") or bool(p.get("dirty")),
                "quelle": "flow-agent", "ausfuehrbar": grund(p["host"]) is None, "grund": grund(p["host"]), "branch": p.get("branch"), "dirty": p.get("dirty"),
                "technologien": p.get("technologien"), "graphify_stand": g.get("generiert"),
            })
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
            out.append({"host": w["host"], "pfad": pfad, "name": r.get("name"), "aktiv": bool(r.get("aktiv")), "quelle": "werkstatt", "ausfuehrbar": grund(w["host"]) is None, "grund": grund(w["host"])})
    if not out:
        for host, basis in cfg.work_dirs.items():
            out.append({"host": host, "pfad": basis, "name": _projekt_name(basis), "aktiv": True, "quelle": "work_dirs", "ausfuehrbar": grund(host) is None, "grund": grund(host)})
    out.sort(key=lambda p: (not p.get("ausfuehrbar", True), not p.get("aktiv"), p["host"], p["name"].lower()))
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
    _agent_host_pruefen(cfg, req.host)
    vorlage = next((x for x in auftrag_vorlagen.vorlagen(cfg.auftrag_vorlagen) if x["id"] == "vorschlaege"), None)
    if vorlage is None:
        raise HTTPException(status_code=404, detail="Vorlage »vorschlaege« fehlt")
    name = _projekt_name(req.projekt)
    p, g = _flow_agent_projekt(session, cfg, req.host, req.projekt)
    text = vorlage["text"] + fa.projekt_kontext(p, g)
    a = svc.anlegen(session, titel=vorlage["titel"].replace("{projekt}", name), text=text, host=req.host, projekt=req.projekt.rstrip("/"),
                    projekt_name=name, agent=req.agent, modus="bericht", profil="lesen", prioritaet=2, zeitfenster="sofort", status="geplant")
    crud_audit.write(session, action="auftrag.vorschlaege", target=a.id, after={"projekt": a.projekt, "agent": a.agent})
    return svc.as_dict(a)


def _agent_host_pruefen(cfg: wc.WallConfig, host: str) -> None:
    if host not in cfg.agent_hosts:
        raise HTTPException(status_code=422, detail=f"Auf Host »{host}« sind keine Agenten installiert – bitte die Kopie des Projekts auf {', '.join(cfg.agent_hosts) or 'einem Agenten-Host'} wählen")


@router.post("", status_code=201)
async def anlegen(req: AuftragNeu, _=Depends(require_auth), session: Session = Depends(get_session)) -> dict:
    _agent_host_pruefen(wc.load(session), req.host)
    a = svc.anlegen(
        session, titel=req.titel.strip(), text=req.text.strip(), host=req.host, projekt=req.projekt.rstrip("/"),
        projekt_name=_projekt_name(req.projekt), agent=req.agent, modus=req.modus, profil=req.profil, prioritaet=req.prioritaet,
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
        if felder["status"] in ("eingang", "geplant") and a.status in ("fertig", "fehler", "abgebrochen", "rueckfrage", "freigabe", "unterbrochen"):
            felder.update({"beendet": None, "fehler": None, "freigegeben": None})
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
    _agent_host_pruefen(cfg, a.host)
    a = await asyncio.to_thread(svc.starten, session, a, bins={**cfg.agent_bins, 'codex_sandbox': cfg.codex_sandbox})
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
    a = await asyncio.to_thread(svc.starten, session, a, bins={**cfg.agent_bins, 'codex_sandbox': cfg.codex_sandbox}, resume=True, nachfrage=text)
    crud_audit.write(session, action="auftrag.nachfrage", target=a.id, after={"text": text[:300]})
    return svc.as_dict(a)


@router.post("/{auftrag_id}/umsetzen")
async def freigeben(auftrag_id: str, req: Freigabe | None = None, _=Depends(require_auth), session: Session = Depends(get_session)) -> dict:
    """Plan freigeben: dieselbe Sitzung setzt jetzt um (Schreibprofil der Karte)."""
    a = svc.holen(session, auftrag_id)
    if a is None:
        raise HTTPException(status_code=404, detail="Auftrag nicht gefunden")
    if a.status != "freigabe":
        raise HTTPException(status_code=409, detail="Kein Plan zur Freigabe (Status ist nicht »Freigabe«)")
    if not a.session_id:
        raise HTTPException(status_code=409, detail="Keine Sitzung zum Fortsetzen")
    kap = runner.kapazitaet(session)
    if kap["laufend"] >= kap["parallel_max"]:
        raise HTTPException(status_code=409, detail=kap.get("pause_grund") or f"Kapazität erschöpft ({kap['laufend']}/{kap['parallel_max']}) – bitte später freigeben")
    cfg = wc.load(session)
    a = await asyncio.to_thread(svc.umsetzen, session, a, bins={**cfg.agent_bins, 'codex_sandbox': cfg.codex_sandbox}, hinweis=(req.hinweis if req else None))
    crud_audit.write(session, action="auftrag.freigabe", target=a.id, after={"status": a.status, "hinweis": (req.hinweis if req else None)})
    return svc.as_dict(a)


@router.post("/runner")
async def runner_schalten(req: RunnerSchalter, _=Depends(require_auth), session: Session = Depends(get_session)) -> dict:
    """Runner anhalten (z. B. vor dem Herunterfahren des NUC) oder fortsetzen; laufende Aufträge laufen weiter."""
    wc.write_setting(session, "runner_angehalten", bool(req.angehalten))
    crud_audit.write(session, action="auftrag.runner", after={"angehalten": req.angehalten})
    return runner.kapazitaet(session)


@router.post("/{auftrag_id}/fortsetzen")
async def fortsetzen(auftrag_id: str, _=Depends(require_auth), session: Session = Depends(get_session)) -> dict:
    """Unterbrochenen Lauf fortsetzen (Sitzung und Worktree bleiben)."""
    a = svc.holen(session, auftrag_id)
    if a is None:
        raise HTTPException(status_code=404, detail="Auftrag nicht gefunden")
    if a.status != "unterbrochen":
        raise HTTPException(status_code=409, detail="Nur unterbrochene Aufträge lassen sich fortsetzen")
    cfg = wc.load(session)
    _agent_host_pruefen(cfg, a.host)
    kap = runner.kapazitaet(session)
    if kap["laufend"] >= kap["parallel_max"]:
        raise HTTPException(status_code=409, detail=kap.get("pause_grund") or "Kapazität erschöpft – bitte später fortsetzen")
    a = await asyncio.to_thread(svc.fortsetzen, session, a, bins={**cfg.agent_bins, 'codex_sandbox': cfg.codex_sandbox})
    crud_audit.write(session, action="auftrag.fortsetzen", target=a.id, after={"status": a.status})
    return svc.as_dict(a)


@router.post("/{auftrag_id}/aufraeumen")
async def aufraeumen(auftrag_id: str, req: Aufraeumen | None = None, _=Depends(require_auth), session: Session = Depends(get_session)) -> dict:
    """Worktree des Auftrags entfernen (Branch bleibt, außer branch_loeschen)."""
    a = svc.holen(session, auftrag_id)
    if a is None:
        raise HTTPException(status_code=404, detail="Auftrag nicht gefunden")
    if a.status == "laeuft":
        raise HTTPException(status_code=409, detail="Laufender Auftrag – zuerst stoppen")
    a = await asyncio.to_thread(svc.aufraeumen, session, a, branch_loeschen=bool(req.branch_loeschen if req else False))
    crud_audit.write(session, action="auftrag.aufraeumen", target=a.id, after={"branch_loeschen": bool(req.branch_loeschen if req else False)})
    return svc.as_dict(a)


@router.post("/{auftrag_id}/pruefen")
async def pruefen(auftrag_id: str, _=Depends(require_auth), session: Session = Depends(get_session)) -> dict:
    """Qualitätstor erneut ausführen (Prüfbefehle aus .cockpit.yaml oder Manifest-Erkennung im Worktree)."""
    a = svc.holen(session, auftrag_id)
    if a is None:
        raise HTTPException(status_code=404, detail="Auftrag nicht gefunden")
    if a.status == "laeuft" or not a.worktree:
        raise HTTPException(status_code=409, detail="Prüfung nur für beendete Aufträge mit Worktree")
    a = await asyncio.to_thread(svc.pruefen, session, a)
    crud_audit.write(session, action="auftrag.pruefen", target=a.id, after={"pruefung_ok": a.pruefung_ok})
    return svc.as_dict(a)


@router.post("/{auftrag_id}/pr")
async def pr_erstellen(auftrag_id: str, _=Depends(require_auth), session: Session = Depends(get_session)) -> dict:
    """Pull Request anlegen (Branch pushen, gh pr create). Das Cockpit mergt nie."""
    a = svc.holen(session, auftrag_id)
    if a is None:
        raise HTTPException(status_code=404, detail="Auftrag nicht gefunden")
    if a.status not in ("fertig", "rueckfrage") or not a.branch:
        raise HTTPException(status_code=409, detail="PR nur für beendete Aufträge mit Branch")
    if a.pr_url:
        raise HTTPException(status_code=409, detail=f"PR existiert bereits: {a.pr_url}")
    a = await asyncio.to_thread(svc.pr_erstellen, session, a)
    crud_audit.write(session, action="auftrag.pr", target=a.id, after={"pr_url": a.pr_url, "fehler": a.fehler})
    if not a.pr_url:
        raise HTTPException(status_code=502, detail=a.fehler or "PR nicht angelegt")
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
