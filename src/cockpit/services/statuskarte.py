"""Statuskarte fuer Push-Nachrichten: ein Bild im Look der Wand (Pillow).

Kopf mit Instanz und Zeit, je Alarm eine Zeile mit farbigem Punkt und Hinweis,
darunter Verlaufslinien der betroffenen Kennzahlen (24 h) und eine Fusszeile mit
Zusammenfassung. Faellt Pillow oder eine Schrift aus, liefert render() None und der
Versand faellt auf reinen Text zurueck.
"""

from __future__ import annotations

import io
import logging
import textwrap
from datetime import datetime

log = logging.getLogger(__name__)

FARBEN = {
    "grund": (11, 16, 32), "flaeche": (19, 26, 46), "linie": (38, 48, 84),
    "text": (231, 236, 247), "text2": (170, 179, 207), "text3": (127, 137, 171),
    "akzent": (242, 184, 75), "ok": (76, 195, 138), "warn": (242, 184, 75),
    "krit": (242, 109, 109), "info": (111, 168, 255),
}
BREITE = 960
_FONT_DIRS = ("/usr/share/fonts/truetype/dejavu", "/usr/share/fonts/dejavu", "/usr/share/fonts/TTF")


def _font(size: int, fett: bool = False):
    from PIL import ImageFont

    name = "DejaVuSans-Bold.ttf" if fett else "DejaVuSans.ttf"
    for d in _FONT_DIRS:
        try:
            return ImageFont.truetype(f"{d}/{name}", size)
        except OSError:
            continue
    return ImageFont.load_default()


def _linie(draw, werte: list[float], x: int, y: int, w: int, h: int, farbe) -> None:
    if len(werte) < 2:
        return
    lo, hi = min(werte), max(werte)
    span = hi - lo or 1.0
    punkte = [(x + i * w / (len(werte) - 1), y + h - (v - lo) / span * (h - 4) - 2) for i, v in enumerate(werte)]
    draw.line(punkte, fill=farbe, width=2)
    px, py = punkte[-1]
    draw.ellipse((px - 3, py - 3, px + 3, py + 3), fill=farbe)


def render(
    *,
    instanz: str,
    hinzu: list[dict],
    weg: list[str],
    zusammenfassung: dict,
    verlaeufe: list[dict],
    wand_url: str,
    zeit: datetime | None = None,
) -> bytes | None:
    """PNG der Statuskarte. verlaeufe: [{label, werte: [float], einheit}] (max. 4)."""
    try:
        from PIL import Image, ImageDraw
    except ImportError:
        log.warning("Pillow fehlt – Statuskarte nicht verfuegbar")
        return None
    f_titel, f_sub, f_zeile, f_klein, f_kpi = _font(28, True), _font(15), _font(19, True), _font(15), _font(22, True)
    zeilen: list[tuple[str, str, str | None]] = []
    for a in hinzu:
        zeilen.append((a.get("level") or "info", str(a.get("text") or ""), a.get("hint")))
    for k in weg:
        _, _, text = k.partition("|")
        zeilen.append(("ok", f"entwarnt: {text}", None))
    if not zeilen:
        zeilen.append(("ok", "Alles läuft – keine offenen Punkte", None))
    # Hoehe berechnen: je Zeile ca. 30 px + Hinweis 22 px + Umbrueche
    umbrueche = [textwrap.wrap(t, 62) or [""] for _, t, _ in zeilen]
    h_zeilen = sum(30 * len(u) + (22 if h else 0) + 8 for (_, _, h), u in zip(zeilen, umbrueche, strict=False))
    h_verlauf = 150 if verlaeufe else 0
    hoehe = 110 + h_zeilen + h_verlauf + 70
    img = Image.new("RGB", (BREITE, hoehe), FARBEN["grund"])
    d = ImageDraw.Draw(img)
    # Kopf
    d.rectangle((0, 0, BREITE, 88), fill=FARBEN["flaeche"])
    d.rectangle((0, 88, BREITE, 90), fill=FARBEN["akzent"])
    d.text((32, 22), "FLOWAUDIT", font=f_titel, fill=FARBEN["text"])
    d.text((32 + d.textlength("FLOWAUDIT", font=f_titel) + 18, 34), "COCKPIT", font=f_sub, fill=FARBEN["text3"])
    zeit = zeit or datetime.now()
    kopf_r = f"{instanz}  ·  {zeit.strftime('%d.%m.%Y %H:%M')}"
    d.text((BREITE - 32 - d.textlength(kopf_r, font=f_sub), 34), kopf_r, font=f_sub, fill=FARBEN["text2"])
    # Alarmzeilen
    y = 112
    for (level, _, hint), u in zip(zeilen, umbrueche, strict=False):
        farbe = FARBEN.get(level, FARBEN["info"])
        d.rectangle((32, y - 4, 36, y + 30 * len(u) + (18 if hint else 0)), fill=farbe)
        d.ellipse((50, y + 7, 62, y + 19), fill=farbe)
        for i, teil in enumerate(u):
            d.text((76, y + i * 30), teil, font=f_zeile, fill=FARBEN["text"])
        y += 30 * len(u)
        if hint:
            d.text((76, y), textwrap.shorten(str(hint), 90), font=f_klein, fill=FARBEN["text3"])
            y += 22
        y += 8
    # Verlaeufe (bis zu 4 nebeneinander)
    if verlaeufe:
        y += 10
        d.text((32, y), "VERLAUF 24 H", font=f_klein, fill=FARBEN["text3"])
        y += 26
        n = min(4, len(verlaeufe))
        bw = (BREITE - 64 - (n - 1) * 16) // n
        for i, v in enumerate(verlaeufe[:n]):
            x = 32 + i * (bw + 16)
            d.rounded_rectangle((x, y, x + bw, y + 100), radius=8, fill=FARBEN["flaeche"], outline=FARBEN["linie"])
            werte = [float(w) for w in v.get("werte") or []]
            d.text((x + 12, y + 8), textwrap.shorten(str(v.get("label") or ""), 28), font=f_klein, fill=FARBEN["text2"])
            if werte:
                aktuell = werte[-1]
                wert_txt = f"{aktuell:,.0f}".replace(",", ".") if aktuell >= 100 else f"{aktuell:.1f}".replace(".", ",")
                d.text((x + 12, y + 28), f"{wert_txt} {v.get('einheit') or ''}".strip(), font=f_kpi, fill=FARBEN["text"])
                _linie(d, werte, x + 12, y + 58, bw - 24, 34, FARBEN["info"])
        y += 110
    # Fusszeile
    d.rectangle((0, hoehe - 52, BREITE, hoehe), fill=FARBEN["flaeche"])
    z = zusammenfassung
    fuss = f"{z.get('krit', 0)} kritisch  ·  {z.get('warn', 0)} prüfen  ·  {z.get('info', 0)} Hinweise  ·  {z.get('hosts_online', 0)}/{z.get('hosts', 0)} Hosts online"
    d.text((32, hoehe - 36), fuss, font=f_klein, fill=FARBEN["text2"])
    d.text((BREITE - 32 - d.textlength(wand_url, font=f_klein), hoehe - 36), wand_url, font=f_klein, fill=FARBEN["text3"])
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


def zusammenfassung_aus_stand(stand: dict) -> dict:
    alerts = stand.get("alerts") or []
    hosts = stand.get("hosts") or []
    return {
        "krit": sum(1 for a in alerts if a.get("level") == "krit"),
        "warn": sum(1 for a in alerts if a.get("level") == "warn"),
        "info": sum(1 for a in alerts if a.get("level") == "info"),
        "hosts": len(hosts),
        "hosts_online": sum(1 for h in hosts if (h.get("stats") or {}).get("ok")),
    }


def verlaeufe_fuer(alerts: list[dict], series: dict[str, list]) -> list[dict]:
    """Passende Verlaeufe zu den Alarmen: Platte/RAM/Last je Host, Antwortzeit je Dienst; sonst Alarmzahlen."""
    out: list[dict] = []
    gesehen: set[str] = set()

    def add(key: str, label: str, einheit: str) -> None:
        if key in series and key not in gesehen and len(series[key]) > 1:
            gesehen.add(key)
            out.append({"label": label, "werte": [p[1] for p in series[key]], "einheit": einheit})

    for a in alerts:
        text = str(a.get("text") or "")
        host = a.get("host")
        if host and "Platte" in text:
            add(f"host.{host}.disk_pct", f"Platte {host}", "%")
        elif host and "RAM" in text:
            add(f"host.{host}.mem_pct", f"RAM {host}", "%")
        elif host and "Last" in text:
            add(f"host.{host}.load1", f"Last {host}", "")
        elif "antwortet" in text or "Zertifikat" in text:
            dienst = text.split(" ")[0] if "antwortet" in text else text.replace("Zertifikat ", "").split(" ")[0]
            add(f"dienst.{dienst}.ms", f"Antwortzeit {dienst}", "ms")
    if not out:
        add("alerts.krit", "Kritische Punkte", "")
        add("alerts.warn", "Zu prüfen", "")
    return out[:4]
