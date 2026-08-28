"""Kurzfassungen für Telegram über das lokale Modell (ai-router, Qwen): Plan, Rückfrage, Ergebnis.

Bewusst klein: ein Aufruf ohne Denkmodus, höchstens ~160 Tokens Antwort, 40 s Zeitlimit.
Fällt der Router aus, kommt der Anfang des Originaltexts – die Nachricht geht immer raus.
"""

from __future__ import annotations

import asyncio
import logging

from . import ai_router_client

log = logging.getLogger(__name__)

ZWECKE = {
    "plan": "Fasse den folgenden Umsetzungsplan eines Programmier-Agenten in höchstens drei kurzen Sätzen zusammen: Was wird geändert, wie groß ist es, welches Risiko. Keine Aufzählung, keine Überschriften.",
    "frage": "Formuliere die Frage des Programmier-Agenten in einem Satz und den nötigen Kontext in einem zweiten Satz. Nichts hinzufügen.",
    "ergebnis": "Fasse das Ergebnis des Programmier-Agenten in höchstens drei kurzen Sätzen zusammen: Was wurde geändert, was ist offen, liefen Tests. Keine Aufzählung.",
}


def fallback(text: str | None, laenge: int = 400) -> str:
    t = " ".join((text or "").split())
    return t if len(t) <= laenge else t[: laenge - 1].rstrip() + "…"


async def kuerzen(text: str | None, zweck: str, *, modell: str | None, aktiv: bool = True, laenge: int = 420) -> str:
    """Kurzfassung per lokalem Modell; ohne Modell/aktiv oder bei Fehlern der gekürzte Originaltext."""
    if not text or not text.strip():
        return ""
    if not aktiv or not modell or len(text) <= laenge:
        return fallback(text, laenge)
    auftrag = ZWECKE.get(zweck, ZWECKE["ergebnis"])
    messages = [
        {"role": "system", "content": "Du schreibst knappe deutsche Kurzfassungen mit echten Umlauten. Antworte nur mit der Kurzfassung."},
        {"role": "user", "content": f"{auftrag}\n\nText:\n{text[:6000]}"},
    ]
    teile: list[str] = []
    try:
        async with asyncio.timeout(40):
            async for chunk in ai_router_client.chat_stream(modell, messages, options={"num_predict": 160, "temperature": 0.2}, think=False):
                if chunk.get("error"):
                    log.warning("Kurzfassung: %s", chunk["error"])
                    return fallback(text, laenge)
                if chunk.get("delta"):
                    teile.append(chunk["delta"])
                if chunk.get("done"):
                    break
    except (TimeoutError, Exception) as exc:  # noqa: BLE001 - Kurzfassung ist Beiwerk
        log.warning("Kurzfassung fehlgeschlagen: %s", exc)
        return fallback(text, laenge)
    kurz = " ".join("".join(teile).split())
    return kurz if kurz else fallback(text, laenge)
