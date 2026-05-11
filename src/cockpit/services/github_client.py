"""GitHub-API-Client via httpx. Verwendet GITHUB_TOKEN aus env.

Wenn kein Token gesetzt: Endpoints werfen GitHubDisabledError → Routes
liefern 503 mit Hinweis.

Cache 60s pro (endpoint, params) — verhindert Rate-Limit-Verbrauch im Polling.
"""
from __future__ import annotations

import logging
import os
import threading
import time
from typing import Any

import httpx

log = logging.getLogger(__name__)

CACHE_TTL_S = 60
API_BASE = "https://api.github.com"

_cache: dict[tuple, tuple[float, Any]] = {}
_lock = threading.Lock()


class GitHubDisabledError(RuntimeError):
    """Wird geworfen, wenn GITHUB_TOKEN nicht gesetzt ist."""


def is_enabled() -> bool:
    return bool(os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN"))


def _token() -> str:
    tok = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if not tok:
        raise GitHubDisabledError("GITHUB_TOKEN nicht gesetzt")
    return tok


def _get(path: str, params: dict | None = None, *, fresh: bool = False) -> Any:
    key = (path, tuple(sorted((params or {}).items())))
    now = time.time()
    with _lock:
        cached = _cache.get(key)
    if cached and not fresh and (now - cached[0]) < CACHE_TTL_S:
        return cached[1]

    headers = {
        "Authorization": f"Bearer {_token()}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "cockpit/0.1",
    }
    try:
        with httpx.Client(base_url=API_BASE, timeout=10.0) as c:
            resp = c.get(path, params=params, headers=headers)
            if resp.status_code == 401:
                raise GitHubDisabledError("GITHUB_TOKEN ist ungueltig (401)")
            if resp.status_code >= 400:
                log.warning("GitHub %s -> %d: %s", path, resp.status_code, resp.text[:200])
                resp.raise_for_status()
            data = resp.json()
    except httpx.RequestError as exc:
        log.warning("GitHub-Request fehlgeschlagen (%s): %s", path, exc)
        raise

    with _lock:
        _cache[key] = (now, data)
    return data


def list_branches(owner: str, name: str) -> list[dict]:
    raw = _get(f"/repos/{owner}/{name}/branches", params={"per_page": 100})
    return [{"name": b.get("name"), "sha": b.get("commit", {}).get("sha", "")[:7]} for b in (raw or [])]


def list_pull_requests(owner: str, name: str, state: str = "open") -> list[dict]:
    raw = _get(f"/repos/{owner}/{name}/pulls", params={"state": state, "per_page": 50})
    out = []
    for p in raw or []:
        out.append({
            "number": p.get("number"),
            "title": p.get("title"),
            "state": p.get("state"),
            "draft": p.get("draft", False),
            "user": (p.get("user") or {}).get("login"),
            "url": p.get("html_url"),
            "created_at": p.get("created_at"),
            "updated_at": p.get("updated_at"),
        })
    return out


def list_workflow_runs(owner: str, name: str, limit: int = 10) -> list[dict]:
    raw = _get(f"/repos/{owner}/{name}/actions/runs", params={"per_page": limit})
    runs = (raw or {}).get("workflow_runs", [])
    out = []
    for r in runs[:limit]:
        out.append({
            "id": r.get("id"),
            "name": r.get("name"),
            "status": r.get("status"),
            "conclusion": r.get("conclusion"),
            "branch": r.get("head_branch"),
            "actor": (r.get("actor") or {}).get("login"),
            "url": r.get("html_url"),
            "created_at": r.get("created_at"),
            "updated_at": r.get("updated_at"),
            "event": r.get("event"),
        })
    return out


def repo_meta(owner: str, name: str) -> dict:
    raw = _get(f"/repos/{owner}/{name}")
    return {
        "full_name": raw.get("full_name"),
        "description": raw.get("description"),
        "default_branch": raw.get("default_branch"),
        "open_issues": raw.get("open_issues_count"),
        "stargazers": raw.get("stargazers_count"),
        "private": raw.get("private"),
        "pushed_at": raw.get("pushed_at"),
        "html_url": raw.get("html_url"),
    }


def dispatch_workflow(owner: str, name: str, workflow_id: str | int, ref: str = "main", inputs: dict | None = None) -> bool:
    """workflow_dispatch trigger. Liefert True bei 204."""
    headers = {
        "Authorization": f"Bearer {_token()}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "cockpit/0.1",
    }
    body = {"ref": ref}
    if inputs:
        body["inputs"] = inputs
    with httpx.Client(base_url=API_BASE, timeout=10.0) as c:
        resp = c.post(f"/repos/{owner}/{name}/actions/workflows/{workflow_id}/dispatches", json=body, headers=headers)
        return resp.status_code == 204
