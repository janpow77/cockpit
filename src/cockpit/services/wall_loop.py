"""Hintergrundlauf der Wand: Stand alle N Sekunden ermitteln, Verlauf schreiben, Alarme pushen.

Die API liefert den zuletzt ermittelten Stand sofort aus (kein Warten auf SSH und
Sonden beim Seitenaufruf); der Lauf haelt ihn frisch. Alarme werden gegen den zuletzt
gemeldeten Stand verglichen und per Telegram verschickt (services/push.py).
"""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime
from zoneinfo import ZoneInfo

from ..db import get_session_factory
from . import push, statuskarte, verlauf
from . import wall_config as wc

log = logging.getLogger(__name__)

_stand: dict | None = None
_stand_ts: float = 0.0
_lock = asyncio.Lock()


def letzter_stand(max_alter_s: float | None = None) -> dict | None:
    if _stand is None:
        return None
    if max_alter_s is not None and time.time() - _stand_ts > max_alter_s:
        return None
    return _stand


async def stand_ermitteln() -> dict:
    """Baut den Stand (mit eigener DB-Sitzung) und merkt ihn als letzten."""
    global _stand, _stand_ts
    from ..routes.overview import build_overview  # spaet, um Kreisimporte zu vermeiden

    async with _lock:
        factory = get_session_factory()
        session = factory()
        try:
            stand = await build_overview(session)
        finally:
            session.close()
        _stand, _stand_ts = stand, time.time()
        return stand


async def _alarme_pushen(stand: dict, cfg: wc.WallConfig) -> None:
    from ..routes.overview import _secret_value

    pcfg = cfg.push or {}
    if not pcfg.get("aktiv"):
        return
    factory = get_session_factory()
    session = factory()
    try:
        alt: list[str] = wc.read_setting(session, "alerts_state", []) or []
        zaehler: dict[str, int] = wc.read_setting(session, "alerts_zaehler", {}) or {}
        min_level = str(pcfg.get("min_level") or "warn")
        laeufe = int(pcfg.get("bestaetigung_laeufe") or 2)
        hinzu, weg, gemeldet_neu, zaehler_neu = push.bestaetigen(alt, zaehler, stand.get("alerts") or [], min_level=min_level, laeufe=laeufe)
        if not hinzu and not weg:
            if zaehler_neu != zaehler:
                wc.write_setting(session, "alerts_zaehler", zaehler_neu)
            return
        tz = ZoneInfo(str(pcfg.get("zeitzone") or "Europe/Berlin"))
        ruhe = push.in_ruhezeit(datetime.now(tz), pcfg.get("ruhe_von"), pcfg.get("ruhe_bis"))
        if ruhe:
            # nachts nur Kritisches; zurückgehaltene Alarme bleiben „bestätigt“ und gehen morgens raus
            hinzu = [a for a in hinzu if a.get("level") == "krit"]
            weg = []
            gemeldet_neu = [k for k in alt if k not in weg] + [push.schluessel(a) for a in hinzu]
        if hinzu or weg:
            token = _secret_value(session, str(pcfg.get("token_secret") or "telegram_bot_token"))
            chat_id = _secret_value(session, str(pcfg.get("chat_secret") or "telegram_chat_id")) or str(pcfg.get("chat_id") or "")
            if token and chat_id:
                instanz = str(pcfg.get("instanz") or next((h.get("name") for h in stand.get("hosts") or [] if h.get("is_self")), "Wand"))
                ok = await karte_senden(session, token, chat_id, instanz, hinzu, weg, stand, cfg)
                log.info("Push: %d neu, %d entwarnt, gesendet=%s", len(hinzu), len(weg), ok)
                if not ok:
                    return
            else:
                log.warning("Push aktiv, aber telegram_bot_token/chat_id fehlen im Vault")
                return
        # Stand nur nach erfolgreichem Versand fortschreiben
        wc.write_setting(session, "alerts_state", gemeldet_neu)
        wc.write_setting(session, "alerts_zaehler", zaehler_neu)
    finally:
        session.close()


async def karte_senden(session, token: str, chat_id: str, instanz: str, hinzu: list[dict], weg: list[str], stand: dict, cfg: wc.WallConfig) -> bool:
    """Statuskarte als Bild mit Kurztext; faellt auf reinen Text zurueck, wenn das Bild nicht entsteht."""
    wand_url = str((cfg.push or {}).get("wand_url") or "")
    try:
        keys = [k for k in verlauf.keys(session) if k.startswith(("host.", "dienst.", "alerts."))]
        series = verlauf.series(session, keys, hours=24, max_points=120) if keys else {}
        png = await asyncio.to_thread(
            statuskarte.render,
            instanz=instanz, hinzu=hinzu, weg=weg,
            zusammenfassung=statuskarte.zusammenfassung_aus_stand(stand),
            verlaeufe=statuskarte.verlaeufe_fuer(hinzu, series), wand_url=wand_url,
        )
    except Exception as exc:  # noqa: BLE001 - Bild ist Beiwerk
        log.warning("Statuskarte: %s", exc)
        png = None
    if png:
        if await push.telegram_foto(token, chat_id, png, push.caption(hinzu, weg, instanz)):
            return True
    return await push.telegram_senden(token, chat_id, push.nachricht(hinzu, weg, instanz))


async def wall_loop(stop_event: asyncio.Event, *, interval_s: int = 90) -> None:
    log.info("Board-Lauf startet (interval=%ds).", interval_s)
    letzte_bereinigung = 0.0
    while not stop_event.is_set():
        try:
            stand = await stand_ermitteln()
            factory = get_session_factory()
            session = factory()
            try:
                cfg = wc.load(session)
                n = verlauf.record(session, stand)
                if time.time() - letzte_bereinigung > 6 * 3600:
                    verlauf.purge(session, days=int(cfg.verlauf_tage))
                    letzte_bereinigung = time.time()
            finally:
                session.close()
            await _alarme_pushen(stand, cfg)
            log.info("Board-Lauf: %d Kennzahlen, %d Alarme", n, len(stand.get("alerts") or []))
        except Exception as exc:  # noqa: BLE001 - der Lauf darf nie sterben
            log.warning("Board-Lauf: %s", exc)
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=interval_s)
        except TimeoutError:
            continue
    log.info("Board-Lauf stoppt.")
