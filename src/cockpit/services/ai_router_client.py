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
ERROR_TTL_S = 5
STALE_TTL_S = 300
_cache: dict[str, tuple[float, object]] = {}
_lock = threading.Lock()
_discovery_lock = threading.Lock()


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


def request_headers() -> dict[str, str]:
    headers = {"X-App-Id": os.environ.get("AI_ROUTER_APP_ID") or "cockpit"}
    if key := os.environ.get("AI_ROUTER_API_KEY"):
        headers["X-Api-Key"] = key
    return headers


def _cached(key: str, ttl: float = CACHE_TTL_S):
    with _lock:
        hit = _cache.get(key)
    if hit and time.monotonic() - hit[0] < ttl:
        return hit[1]
    return None


def _store(key: str, value: object) -> None:
    with _lock:
        _cache[key] = (time.monotonic(), value)


def list_models(*, refresh: bool = False) -> list[dict]:
    """Modelle; bei Stoerungen hoechstens fuenf Minuten alter letzter Stand."""
    return model_snapshot(refresh=refresh)["models"]


def model_snapshot(*, refresh: bool = False) -> dict:
    """Modellliste und Abrufstatus atomar lesen; parallele Abrufe zusammenfassen."""
    with _discovery_lock:
        if not refresh:
            hit = _cached("discovery")
            if hit is not None and _cached("discovery", hit["cache_ttl"]) is not None:
                # Auch ein Fehlercache darf alte Modelle nicht ueber die Frist retten.
                if hit["stale"] and _cached("last_models", STALE_TTL_S) is None:
                    return {**hit, "models": [], "stale": False}
                return hit
        result = _fetch_models()
        _store("discovery", result)
        return result


def _fetch_models() -> dict:
    state, message = "unreachable", "ai-router nicht erreichbar"
    reachable = False
    http_status = None
    retry_after = None
    for url in _candidates():
        try:
            with httpx.Client(timeout=6.0) as c:
                resp = c.get(f"{url}/api/tags", headers=request_headers())
                reachable = True
                _resolved["url"] = url
                http_status = resp.status_code
                resp.raise_for_status()
                daten = resp.json()
                eintraege = daten.get("models") if isinstance(daten, dict) else None
                if not isinstance(eintraege, list):
                    raise ValueError("unerwartete Antwort von /api/tags")
                models: list[dict] = []
                for m in eintraege:
                    if not isinstance(m, dict):
                        continue
                    details = m.get("details") if isinstance(m.get("details"), dict) else {}
                    try:
                        size = int(m.get("size") or 0)
                    except (TypeError, ValueError):
                        size = 0
                    models.append({
                        "name": str(m.get("name") or ""),
                        "parameter_size": str(details.get("parameter_size") or ""),
                        "family": str(details.get("family") or ""),
                        "size_bytes": size,
                    })
        except httpx.HTTPStatusError as exc:
            code = exc.response.status_code
            if code == 429:
                state, message = "overloaded", "ai-router überlastet (HTTP 429) – Modellabruf gedrosselt"
                try:
                    retry_after = max(1, int(exc.response.headers.get("retry-after", "1")))
                except ValueError:
                    retry_after = 1
            elif code in (401, 403):
                state, message = "auth_error", f"ai-router: Zugriff verweigert (HTTP {code})"
            else:
                state, message = "http_error", f"ai-router: Modellabruf fehlgeschlagen (HTTP {code})"
            # Der Router hat geantwortet. Eine andere Adresse desselben Routers
            # behebt weder Quoten noch Auth-Fehler und verdeckt den eigentlichen Fehler.
            break
        except httpx.RequestError as exc:
            log.warning("ai-router Modellabruf %s: %s", url, type(exc).__name__)
            continue
        except (ValueError, TypeError, AttributeError):
            state, message = "invalid_response", "ai-router: ungültige Antwort auf den Modellabruf"
            break
        _store("last_models", models)
        return {
            "ok": bool(models), "reachable": True, "state": "ok" if models else "empty",
            "message": "Router bereit" if models else "ai-router erreichbar, meldet aber keine Modelle",
            "url": url, "models": models, "stale": False, "http_status": http_status,
            "retry_after": None, "cache_ttl": CACHE_TTL_S,
        }
    log.warning("%s", message)
    models = _cached("last_models", STALE_TTL_S) or []
    return {
        "ok": False, "reachable": reachable, "state": state, "message": message,
        "url": base_url(), "models": models, "stale": bool(models), "http_status": http_status,
        "retry_after": retry_after, "cache_ttl": min(CACHE_TTL_S, max(ERROR_TTL_S, retry_after or 0)),
    }


def status() -> dict:
    """{ok, url, model_count, models: [names]} – fuer die Wand."""
    snapshot = model_snapshot()
    return {
        **{k: v for k, v in snapshot.items() if k != "cache_ttl"},
        "model_count": len(snapshot["models"]),
        "models": [m["name"] for m in snapshot["models"]],
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
            async with c.stream("POST", f"{base_url()}/api/chat", json=payload, headers=request_headers()) as resp:
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
