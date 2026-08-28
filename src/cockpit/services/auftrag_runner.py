"""Runner fuer Aufträge: plant nach Priorität und Kontingent, startet Läufe, prüft den Stand.

Alle 20 s: laufende Aufträge nachsehen (Protokoll, Ende → Ergebnis/Commit), dann freie
Kapazität mit geplanten Aufträgen füllen (Priorität, Reihenfolge, Zeitfenster). Kapazität
richtet sich nach der KI-Auslastung aus dem Wand-Stand (Claude: 5-Stunden-Fenster;
Codex: Wochenfenster; Gemini: ein Lauf). Abschluss und Fehler gehen als Push raus.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from ..db import get_session_factory
from . import auftraege as svc
from . import push
from . import wall_config as wc

log = logging.getLogger(__name__)


def _auslastung(stand: dict | None) -> dict:
    ki = (stand or {}).get("ki_nutzung") or {}
    c = (ki.get("claude") or {}).get("limits") or {}
    x = (ki.get("codex") or {}).get("limits") or {}
    return {
        "claude_5h": (c.get("five_hour") or {}).get("prozent"),
        "claude_woche": (c.get("seven_day") or {}).get("prozent"),
        "claude_reset_woche": (c.get("seven_day") or {}).get("reset"),
        "codex_woche": (x.get("primary") or {}).get("prozent"),
    }


def kapazitaet(session: Session, stand: dict | None = None) -> dict:
    from . import wall_loop

    cfg = wc.load(session)
    stand = stand if stand is not None else wall_loop.letzter_stand()
    a = _auslastung(stand)
    maximal, grund = svc.parallel_max(a["claude_5h"], a["claude_woche"], basis=int(cfg.auftrag_parallel))
    laufend = sum(1 for x in svc.liste(session) if x.status == "laeuft")
    return {
        "parallel_max": maximal, "laufend": laufend, "pause_grund": grund,
        "fuenf_stunden_pct": a["claude_5h"], "woche_pct": a["claude_woche"], "codex_woche_pct": a["codex_woche"],
    }


async def _pushen(session: Session, a, cfg: wc.WallConfig) -> None:
    from ..routes.overview import _secret_value

    pcfg = cfg.push or {}
    if not pcfg.get("aktiv"):
        return
    token = _secret_value(session, str(pcfg.get("token_secret") or "telegram_bot_token"))
    chat_id = _secret_value(session, str(pcfg.get("chat_secret") or "telegram_chat_id")) or str(pcfg.get("chat_id") or "")
    if not token or not chat_id:
        return
    symbol = {"fertig": "✅", "rueckfrage": "❓", "fehler": "🔴", "abgebrochen": "⏹"}.get(a.status, "•")
    zeilen = [f"{symbol} Auftrag {a.status}: {a.titel}", f"{a.agent} · {a.projekt_name} auf {a.host}"]
    if a.dauer_s:
        zeilen.append(f"Dauer {a.dauer_s // 60} min {a.dauer_s % 60} s" + (f" · {a.kosten_usd:.2f} $" if a.kosten_usd else ""))
    if a.status == "fehler" and a.fehler:
        zeilen.append(a.fehler[:300])
    elif a.ergebnis:
        zeilen.append(a.ergebnis[:600])
    if a.diff_url:
        zeilen.append(a.diff_url)
    await push.telegram_senden(token, chat_id, "\n".join(zeilen)[:3900])


def vorschlagslaeufe_planen(session: Session, cfg: wc.WallConfig, stand: dict | None) -> int:
    """Einmal je Woche (Wochentag/Stunde aus cfg.vorschlaege) einen Vorschlags-Lauf je aktivem Projekt anlegen (Status geplant, Zeitfenster nachts)."""
    from . import auftrag_vorlagen

    v = cfg.vorschlaege or {}
    if not v.get("aktiv"):
        return 0
    tz = ZoneInfo(str((cfg.push or {}).get("zeitzone") or "Europe/Berlin"))
    jetzt = datetime.now(tz)
    if jetzt.weekday() != int(v.get("wochentag", 6)) or jetzt.hour != int(v.get("stunde", 1)):
        return 0
    woche = jetzt.strftime("%G-KW%V")
    vorlage = next((x for x in auftrag_vorlagen.vorlagen(cfg.auftrag_vorlagen) if x["id"] == "vorschlaege"), None)
    if vorlage is None:
        return 0
    vorhanden = {(a.projekt, a.titel) for a in svc.liste(session) if a.erstellt[:10] >= (jetzt.replace(hour=0, minute=0).isoformat()[:10])}
    n = 0
    for w in (stand or {}).get("werkstatt") or []:
        basis = cfg.work_dirs.get(w.get("host") or "")
        if not basis:
            continue
        for repo in w.get("repos") or []:
            if not repo.get("aktiv"):
                continue
            pfad = f"{basis.rstrip('/')}/{repo.get('name')}"
            titel = vorlage["titel"].replace("{projekt}", str(repo.get("name"))) + f" ({woche})"
            if (pfad, titel) in vorhanden:
                continue
            svc.anlegen(session, titel=titel, text=vorlage["text"], host=w["host"], projekt=pfad, projekt_name=str(repo.get("name")),
                        agent=str(v.get("agent") or "claude"), profil="lesen", prioritaet=4, zeitfenster="nachts", status="geplant")
            n += 1
    if n:
        log.info("%d Vorschlagsläufe für %s eingeplant", n, woche)
    return n


async def runde() -> None:
    from . import wall_loop

    factory = get_session_factory()
    session = factory()
    try:
        cfg = wc.load(session)
        stand = wall_loop.letzter_stand()
        github_url = None
        # 1. laufende Aufträge nachsehen
        for a in [x for x in svc.liste(session) if x.status == "laeuft"]:
            vorher = a.status
            repo_url = next((r.get("html_url") for r in ((stand or {}).get("github") or {}).get("repos") or [] if r.get("name") == a.projekt_name), None)
            a = await asyncio.to_thread(svc.stand_pruefen, session, a, repo_url or github_url)
            if a.status != vorher:
                log.info("Auftrag %s: %s → %s", a.id, vorher, a.status)
                if a.status == "fertig" and svc.ist_vorschlagslauf(a):
                    n = svc.vorschlaege_eintragen(session, a)
                    if n:
                        a = svc.aendern(session, a, ergebnis=f"{n} Vorschläge in den Eingang gelegt.\n\n{a.ergebnis or ''}")
                await _pushen(session, a, cfg)
        # 1b. wöchentliche Vorschlagsläufe für aktive Projekte einplanen
        try:
            vorschlagslaeufe_planen(session, cfg, stand)
        except Exception as exc:  # noqa: BLE001
            log.warning("Vorschlagsläufe planen: %s", exc)
        # 2. freie Kapazität füllen
        kap = kapazitaet(session, stand)
        frei = kap["parallel_max"] - kap["laufend"]
        if frei <= 0:
            return
        tz = ZoneInfo(str((cfg.push or {}).get("zeitzone") or "Europe/Berlin"))
        jetzt = datetime.now(tz)
        reset = None
        r = _auslastung(stand).get("claude_reset_woche")
        if r:
            try:
                reset = datetime.fromisoformat(str(r).replace("Z", "+00:00")).astimezone(tz)
            except ValueError:
                reset = None
        geplant = sorted((x for x in svc.liste(session) if x.status == "geplant"), key=lambda x: (x.prioritaet, x.reihenfolge, x.erstellt))
        for a in geplant:
            if frei <= 0:
                break
            if not svc.zeitfenster_offen(a.zeitfenster, jetzt, reset):
                continue
            if a.agent == "gemini" and any(x.status == "laeuft" and x.agent == "gemini" for x in svc.liste(session)):
                continue
            a = await asyncio.to_thread(svc.starten, session, a, bins=dict(cfg.agent_bins))
            log.info("Auftrag %s gestartet (%s, %s): %s", a.id, a.agent, a.profil, a.status)
            if a.status == "laeuft":
                frei -= 1
            else:
                await _pushen(session, a, cfg)
    finally:
        session.close()


async def runner_loop(stop_event: asyncio.Event, *, interval_s: int = 20) -> None:
    log.info("Auftrags-Runner startet (interval=%ds).", interval_s)
    while not stop_event.is_set():
        try:
            await runde()
        except Exception as exc:  # noqa: BLE001 - der Runner darf nie sterben
            log.warning("Auftrags-Runner: %s", exc)
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=interval_s)
        except TimeoutError:
            continue
    log.info("Auftrags-Runner stoppt.")
