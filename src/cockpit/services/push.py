"""Push-Alarme der Wand: neue kritische/pruefenswerte Punkte per Telegram, Entwarnung bei Wegfall.

Der Vergleich laeuft gegen den zuletzt gemeldeten Stand (Setting ``alerts_state``),
damit ein Neustart nichts doppelt meldet. Ruhezeiten unterdruecken Warnungen nachts;
Kritisches geht immer raus. Der Bot-Token liegt im Vault (``telegram_bot_token``).
"""

from __future__ import annotations

import logging
from datetime import datetime

import httpx

log = logging.getLogger(__name__)

TELEGRAM_API = "https://api.telegram.org/bot{token}/sendMessage"
_RANG = {"krit": 0, "warn": 1, "info": 2}


def schluessel(alert: dict) -> str:
    return f"{alert.get('level')}|{alert.get('text')}"


def vergleich(alt: list[str], neu: list[dict], *, min_level: str = "warn") -> tuple[list[dict], list[str]]:
    """Neue Alarme ab min_level und weggefallene (Entwarnung) gegenueber dem letzten Stand (rein, testbar)."""
    grenze = _RANG.get(min_level, 1)
    relevant = [a for a in neu if _RANG.get(a.get("level"), 9) <= grenze]
    neu_keys = {schluessel(a) for a in relevant}
    alt_set = set(alt)
    hinzu = [a for a in relevant if schluessel(a) not in alt_set]
    weg = [k for k in alt if k not in neu_keys]
    return hinzu, weg


def in_ruhezeit(jetzt: datetime, von: str | None, bis: str | None) -> bool:
    """Ruhezeit 'HH:MM'–'HH:MM', auch ueber Mitternacht (rein, testbar)."""
    if not von or not bis:
        return False
    try:
        v = int(von[:2]) * 60 + int(von[3:5])
        b = int(bis[:2]) * 60 + int(bis[3:5])
    except ValueError:
        return False
    m = jetzt.hour * 60 + jetzt.minute
    return (v <= m < b) if v <= b else (m >= v or m < b)


def nachricht(hinzu: list[dict], weg: list[str], instanz: str) -> str:
    """Telegram-Text (Markdown aus, reiner Text mit Symbolen)."""
    zeilen = [f"Cockpit {instanz}"]
    for a in sorted(hinzu, key=lambda x: _RANG.get(x.get("level"), 9)):
        symbol = "🔴" if a.get("level") == "krit" else ("🟠" if a.get("level") == "warn" else "🔵")
        zeile = f"{symbol} {a.get('text')}"
        if a.get("hint"):
            zeile += f" – {a['hint']}"
        zeilen.append(zeile)
    for k in weg:
        level, _, text = k.partition("|")
        zeilen.append(f"✅ entwarnt: {text}")
    return "\n".join(zeilen)[:3900]


async def telegram_senden(token: str, chat_id: str, text: str) -> bool:
    try:
        async with httpx.AsyncClient(timeout=15.0) as c:
            resp = await c.post(TELEGRAM_API.format(token=token), json={"chat_id": chat_id, "text": text, "disable_web_page_preview": True})
        if resp.status_code >= 400:
            log.warning("Telegram: HTTP %s %s", resp.status_code, resp.text[:120])
            return False
        return True
    except httpx.HTTPError as exc:
        log.warning("Telegram nicht erreichbar: %s", exc)
        return False
