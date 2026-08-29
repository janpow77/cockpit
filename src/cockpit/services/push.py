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
TELEGRAM_FOTO = "https://api.telegram.org/bot{token}/sendPhoto"
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


def bestaetigen(
    gemeldet: list[str], zaehler: dict[str, int], neu: list[dict], *, min_level: str = "warn", laeufe: int = 2,
) -> tuple[list[dict], list[str], list[str], dict[str, int]]:
    """Alarme erst nach ``laeufe`` aufeinanderfolgenden Wand-Läufen melden und erst nach ebenso vielen
    Läufen ohne den Alarm entwarnen – kurze Aussetzer (ConnectTimeout, Neustart) lösen nichts aus (rein, testbar).

    Liefert (hinzu, weg, gemeldet_neu, zaehler_neu). ``zaehler`` zählt je Schlüssel, wie oft ein noch nicht
    gemeldeter Alarm in Folge auftrat (positiv) bzw. wie oft ein gemeldeter Alarm in Folge fehlte (negativ).
    """
    laeufe = max(1, int(laeufe))
    grenze = _RANG.get(min_level, 1)
    relevant = {schluessel(a): a for a in neu if _RANG.get(a.get("level"), 9) <= grenze}
    gemeldet_set = set(gemeldet)
    z: dict[str, int] = {}
    hinzu: list[dict] = []
    weg: list[str] = []
    # noch nicht gemeldete Alarme: hochzählen, ab `laeufe` melden
    for key, a in relevant.items():
        if key in gemeldet_set:
            continue
        n = max(0, int(zaehler.get(key, 0))) + 1
        if n >= laeufe:
            hinzu.append(a)
        else:
            z[key] = n
    # gemeldete Alarme, die fehlen: runterzählen, ab `laeufe` entwarnen
    for key in gemeldet:
        if key in relevant:
            continue
        n = min(0, int(zaehler.get(key, 0))) - 1
        if -n >= laeufe:
            weg.append(key)
        else:
            z[key] = n
    gemeldet_neu = [k for k in gemeldet if k not in weg] + [schluessel(a) for a in hinzu]
    return hinzu, weg, gemeldet_neu, z


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


def caption(hinzu: list[dict], weg: list[str], instanz: str) -> str:
    """Kurztext zur Statuskarte (Telegram-HTML, max. 1024 Zeichen)."""
    import html

    teile = [f"<b>Cockpit {html.escape(instanz)}</b>"]
    for a in sorted(hinzu, key=lambda x: _RANG.get(x.get("level"), 9))[:6]:
        symbol = "🔴" if a.get("level") == "krit" else ("🟠" if a.get("level") == "warn" else "🔵")
        teile.append(f"{symbol} {html.escape(str(a.get('text') or ''))}")
    for k in weg[:4]:
        teile.append(f"✅ entwarnt: {html.escape(k.partition('|')[2])}")
    rest = len(hinzu) - 6 + max(0, len(weg) - 4)
    if rest > 0:
        teile.append(f"… und {rest} weitere")
    return "\n".join(teile)[:1000]


async def telegram_foto(token: str, chat_id: str, png: bytes, caption_html: str) -> bool:
    try:
        async with httpx.AsyncClient(timeout=25.0) as c:
            resp = await c.post(
                TELEGRAM_FOTO.format(token=token),
                data={"chat_id": chat_id, "caption": caption_html, "parse_mode": "HTML"},
                files={"photo": ("cockpit.png", png, "image/png")},
            )
        if resp.status_code >= 400:
            log.warning("Telegram-Foto: HTTP %s %s", resp.status_code, resp.text[:120])
            return False
        return True
    except httpx.HTTPError as exc:
        log.warning("Telegram-Foto nicht erreichbar: %s", exc)
        return False
