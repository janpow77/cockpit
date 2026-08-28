"""Minimaler MCP-Client (Streamable HTTP, JSON-RPC) fuer die MCP-Seite.

Kann: initialize -> tools/list -> tools/call (z. B. `skills_list`). Antworten
kommen als JSON oder als SSE-Strom (data:-Zeilen); beides wird gelesen.
Nur lesend, mit Timeout, ohne Ausnahme nach aussen: Ergebnis traegt `ok`
und `error`, damit die Seite den Zustand ruhig anzeigen kann.
"""

from __future__ import annotations

import json
import logging
from typing import Any

import httpx

log = logging.getLogger(__name__)

PROTOCOL = "2025-03-26"
TIMEOUT = httpx.Timeout(12.0, connect=6.0)


def _parse_body(resp: httpx.Response) -> dict | None:
    """JSON-RPC-Antwort aus JSON- oder SSE-Body ziehen."""
    ctype = resp.headers.get("content-type", "")
    text = resp.text
    if "text/event-stream" in ctype:
        letzte: dict | None = None
        for line in text.splitlines():
            if line.startswith("data:"):
                try:
                    obj = json.loads(line[5:].strip())
                except json.JSONDecodeError:
                    continue
                if isinstance(obj, dict) and ("result" in obj or "error" in obj):
                    letzte = obj
        return letzte
    try:
        obj = resp.json()
    except ValueError:
        return None
    return obj if isinstance(obj, dict) else None


class McpHttp:
    def __init__(self, url: str, headers: dict[str, str] | None = None) -> None:
        self.url = url
        self.headers = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json", **(headers or {})}
        self.session_id: str | None = None
        self._id = 0

    def _call(self, client: httpx.Client, method: str, params: dict | None = None, *, notify: bool = False) -> dict | None:
        self._id += 1
        body: dict[str, Any] = {"jsonrpc": "2.0", "method": method, "params": params or {}}
        if not notify:
            body["id"] = self._id
        headers = dict(self.headers)
        if self.session_id:
            headers["Mcp-Session-Id"] = self.session_id
        resp = client.post(self.url, json=body, headers=headers)
        sid = resp.headers.get("mcp-session-id")
        if sid:
            self.session_id = sid
        if notify:
            return None
        if resp.status_code >= 400:
            raise RuntimeError(f"HTTP {resp.status_code}: {resp.text[:160]}")
        parsed = _parse_body(resp)
        if parsed is None:
            raise RuntimeError("keine JSON-RPC-Antwort")
        if parsed.get("error"):
            raise RuntimeError(str(parsed["error"].get("message") or parsed["error"])[:200])
        return parsed.get("result") or {}

    def inspect(self, *, skills_tool: str | None = "skills_list") -> dict:
        out: dict[str, Any] = {"ok": False, "error": None, "server": None, "tools": [], "skills": None}
        try:
            with httpx.Client(timeout=TIMEOUT) as client:
                init = self._call(client, "initialize", {
                    "protocolVersion": PROTOCOL,
                    "capabilities": {},
                    "clientInfo": {"name": "cockpit", "version": "0.3"},
                }) or {}
                out["server"] = init.get("serverInfo") or {}
                out["protocol"] = init.get("protocolVersion")
                try:
                    self._call(client, "notifications/initialized", notify=True)
                except httpx.HTTPError:
                    pass
                tools = (self._call(client, "tools/list") or {}).get("tools", [])
                out["tools"] = [
                    {"name": t.get("name", ""), "description": (t.get("description") or "").strip().split("\n")[0][:160]}
                    for t in tools
                ]
                names = {t["name"] for t in out["tools"]}
                if skills_tool and skills_tool in names:
                    res = self._call(client, "tools/call", {"name": skills_tool, "arguments": {}}) or {}
                    out["skills"] = _skills_aus_result(res)
                out["ok"] = True
        except (httpx.HTTPError, RuntimeError, ValueError) as exc:
            out["error"] = str(exc)[:200]
        return out


def _skills_aus_result(res: dict) -> list[dict] | dict | str | None:
    """Text-Content eines tools/call-Ergebnisses als JSON deuten, sonst Rohtext."""
    for c in res.get("content") or []:
        if c.get("type") == "text":
            text = c.get("text") or ""
            try:
                obj = json.loads(text)
            except json.JSONDecodeError:
                return text[:4000]
            if isinstance(obj, dict) and isinstance(obj.get("result"), str):
                try:
                    obj = json.loads(obj["result"])
                except json.JSONDecodeError:
                    return obj["result"][:4000]
            return obj
    return None


def claude_code_snippet(name: str, url: str, header: str | None, header_prefix: str) -> str:
    """Fertiger Befehl fuer Claude Code (Wert des Secrets als Platzhalter)."""
    if header:
        return f'claude mcp add --transport http {name} {url} --header "{header}: {header_prefix}<SECRET>"'
    return f"claude mcp add --transport http {name} {url}"
