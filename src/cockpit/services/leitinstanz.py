"""Leitinstanz: eine Instanz (Hetzner) hält Aufträge, Vault-Dialog und Runner – die anderen reichen /admin/api/auftraege durch.

Einstellung ``leitinstanz`` = {url, benutzer_secret, passwort_secret}. Ist ``url`` gesetzt, meldet sich diese
Instanz mit den Vault-Werten bei der Leitinstanz an (Token gecacht, bei 401 einmal erneuert) und leitet
jede Anfrage unter /admin/api/auftraege weiter – nach Prüfung der *lokalen* Anmeldung. Runner und
Telegram-Dialog bleiben dann hier aus. Die Wand bleibt lokal (jede Instanz sieht ihr Netz).
"""

from __future__ import annotations

import logging
import threading
import time

import httpx

log = logging.getLogger(__name__)

PRAEFIX = "/admin/api/auftraege"
_token: dict[str, tuple[str, float]] = {}
_lock = threading.Lock()


def betrifft(pfad: str) -> bool:
    """Wird dieser Pfad an die Leitinstanz durchgereicht? (rein, testbar)"""
    return pfad == PRAEFIX or pfad.startswith(PRAEFIX + "/")


def ziel_url(basis: str, pfad: str, query: str | None) -> str:
    return f"{basis.rstrip('/')}{pfad}" + (f"?{query}" if query else "")


def url_aus(cfg_leitinstanz: dict | None) -> str | None:
    url = str((cfg_leitinstanz or {}).get("url") or "").strip()
    return url or None


async def token_holen(basis: str, benutzer: str, passwort: str, *, erneuern: bool = False) -> str | None:
    """Anmeldung bei der Leitinstanz; Token 50 min gecacht."""
    now = time.time()
    with _lock:
        c = _token.get(basis)
    if c and not erneuern and c[1] > now:
        return c[0]
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(20.0, connect=8.0)) as client:
            r = await client.post(f"{basis.rstrip('/')}/admin/api/auth/login", json={"username": benutzer, "password": passwort})
        if r.status_code >= 400:
            log.warning("Leitinstanz-Anmeldung: HTTP %s", r.status_code)
            return None
        tok = str((r.json() or {}).get("token") or "")
    except (httpx.HTTPError, ValueError) as exc:
        log.warning("Leitinstanz nicht erreichbar: %s", exc)
        return None
    if not tok:
        return None
    with _lock:
        _token[basis] = (tok, now + 50 * 60)
    return tok


async def weiterleiten(basis: str, token: str, methode: str, pfad: str, query: str | None, body: bytes, content_type: str | None) -> httpx.Response:
    headers = {"Authorization": f"Bearer {token}"}
    if content_type:
        headers["Content-Type"] = content_type
    async with httpx.AsyncClient(timeout=httpx.Timeout(190.0, connect=8.0)) as client:
        return await client.request(methode, ziel_url(basis, pfad, query), content=body if body else None, headers=headers)
