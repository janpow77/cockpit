"""Client fuer den ai-router (Ollama-kompatible API: /api/tags, /api/chat).

Der Router laeuft Tailscale-only (Standard: ccx23:7842). Lesende Aufrufe
(Modellliste, Status) werden kurz gecacht; der Chat streamt NDJSON-Zeilen
1:1 an den Aufrufer weiter (Tokens, am Ende die Zaehler).
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from collections.abc import AsyncIterator

import httpx

log = logging.getLogger(__name__)

DEFAULT_URL = "http://100.99.159.80:7842"
CACHE_TTL_S = 60
_cache: dict[str, tuple[float, object]] = {}
_lock = threading.Lock()


# Ohne AI_ROUTER_URL werden diese Adressen der Reihe nach probiert: im Container auf
# ccx23 haengt der Router im selben Docker-Netz (ai-router), sonst Tailscale.
FALLBACK_URLS = ("http://ai-router:7842", DEFAULT_URL)
_resolved: dict[str, str] = {}


def base_url() -> str:
    env = os.environ.get("AI_ROUTER_URL")
    if env:
        return env.rstrip("/")
    return _resolved.get("url") or DEFAULT_URL


def _candidates() -> tuple[str, ...]:
    env = os.environ.get("AI_ROUTER_URL")
    if env:
        return (env.rstrip("/"),)
    gemerkt = _resolved.get("url")
    rest = tuple(u for u in FALLBACK_URLS if u != gemerkt)
    return ((gemerkt,) + rest) if gemerkt else rest


def _cached(key: str):
    with _lock:
        hit = _cache.get(key)
    if hit and time.time() - hit[0] < CACHE_TTL_S:
        return hit[1]
    return None


def _store(key: str, value: object) -> None:
    with _lock:
        _cache[key] = (time.time(), value)


def list_models(*, refresh: bool = False) -> list[dict]:
    """[{name, parameter_size, size_bytes, family}] – leer bei Fehler."""
    if not refresh:
        hit = _cached("models")
        if hit is not None:
            return hit  # type: ignore[return-value]
    models: list[dict] = []
    letzter_fehler: Exception | None = None
    for url in _candidates():
        try:
            with httpx.Client(timeout=6.0) as c:
                resp = c.get(f"{url}/api/tags")
                resp.raise_for_status()
                for m in resp.json().get("models", []):
                    details = m.get("details") or {}
                    models.append({
                        "name": m.get("name", ""),
                        "parameter_size": details.get("parameter_size", ""),
                        "family": details.get("family", ""),
                        "size_bytes": int(m.get("size") or 0),
                    })
        except (httpx.HTTPError, ValueError) as exc:
            letzter_fehler = exc
            models = []
            continue
        _resolved["url"] = url
        break
    if letzter_fehler is not None and not models:
        log.warning("ai-router /api/tags nicht erreichbar (%s): %s", ", ".join(_candidates()), letzter_fehler)
        return models
    _store("models", models)
    return models


def status() -> dict:
    """{ok, url, model_count, models: [names]} – fuer die Wand."""
    models = list_models()
    return {
        "ok": bool(models),
        "url": base_url(),
        "model_count": len(models),
        "models": [m["name"] for m in models],
    }


async def chat_stream(
    model: str,
    messages: list[dict],
    *,
    options: dict | None = None,
    think: bool | None = None,
) -> AsyncIterator[dict]:
    """Streamt /api/chat als Folge von Dicts: {"delta": str} je Token,
    zum Schluss {"done": True, "eval_count", "eval_duration_ms", "prompt_eval_count"}.
    Fehler werden als {"error": str} geliefert, nie als Exception nach aussen."""
    payload = {"model": model, "messages": messages, "stream": True}
    if options:
        payload["options"] = options
    if think is not None:
        # Ollama: Denkmodus der Qwen-Modelle abschalten -> Antwort in Sekunden statt Minuten
        payload["think"] = think
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(600.0, connect=10.0)) as c:
            async with c.stream("POST", f"{base_url()}/api/chat", json=payload) as resp:
                if resp.status_code >= 400:
                    body = (await resp.aread())[:300].decode("utf-8", "replace")
                    yield {"error": f"ai-router antwortete {resp.status_code}: {body}"}
                    return
                async for line in resp.aiter_lines():
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        obj = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if obj.get("error"):
                        yield {"error": str(obj["error"])[:300]}
                        return
                    delta = (obj.get("message") or {}).get("content") or ""
                    if delta:
                        yield {"delta": delta}
                    if obj.get("done"):
                        yield {
                            "done": True,
                            "eval_count": obj.get("eval_count"),
                            "prompt_eval_count": obj.get("prompt_eval_count"),
                            "eval_duration_ms": int((obj.get("eval_duration") or 0) / 1_000_000),
                            "total_duration_ms": int((obj.get("total_duration") or 0) / 1_000_000),
                        }
                        return
    except httpx.HTTPError as exc:
        yield {"error": f"ai-router nicht erreichbar: {exc}"}
