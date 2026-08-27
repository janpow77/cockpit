"""Konfiguration der Wand (Leitstand/Landschaft) und der KI-Konsole.

Alles liegt als JSON in cockpit_settings; Vorgaben decken den heutigen
Betrieb ab und sind ueber die Einstellungen aenderbar. Grundsatz: Auf die
Wand kommt nur, was nicht in `hide` steht - Vault, Secrets und private
Projekte bleiben unsichtbar.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.orm import Session

from ..models import SettingRow

# Projekt-/Containernamen (Teilstring, Gross-/Kleinschreibung egal), die nie
# auf der Wand erscheinen. Bewusst konservativ vorbelegt.
DEFAULT_HIDE: list[str] = [
    "love-ai", "x_chat", "sarah", "kino", "mediaarchiv", "portainer",
    "buildx_buildkit", "watchtower", "persona", "16personalities", "wesenszug", "tmp",
]

# Oeffentliche Adressen je Projekt (Compose-Projekt oder Container-Praefix).
DEFAULT_LINKS: dict[str, str] = {
    "regulierung": "https://hpp.flowaudit.de",
    "hpp": "https://hpp.flowaudit.de",
    "checklist": "https://checklist.flowaudit.de",
    "auditworkshop": "https://workshop.flowaudit.de",
    "checklist-mcp-memory": "https://mcp.flowaudit.de",
    "flow-agent": "https://agent.flowaudit.de",
    "pdfapp": "https://pdf.flowaudit.de",
    "ki-pilotprogramm": "https://pilot.flowaudit.de",
    "zvg": "https://zvg.flowaudit.de",
    "rl_": "https://seminar.flowaudit.de",
}

# Sprechende Namen und Kurzbeschreibungen fuer bekannte Projekte.
DEFAULT_LABELS: dict[str, dict[str, str]] = {
    "regulierung": {"title": "HPP · Preismonitoring-Portal", "sub": "KPAnG-Vollzug und Marktbeobachtung"},
    "hpp": {"title": "HPP · Preismonitoring-Portal", "sub": "KPAnG-Vollzug und Marktbeobachtung"},
    "checklist": {"title": "Checklisten-Designer", "sub": "EFRE-Prüfung · audit_designer"},
    "auditworkshop": {"title": "Workshop", "sub": "Seminar-Plattform"},
    "flowinvoice": {"title": "flowinvoice", "sub": "Belegprüfung mit Erkennung"},
    "ai-router": {"title": "ai-router", "sub": "LLM-Gateway · Spokes EVO/NUC"},
    "checklist-mcp-memory": {"title": "Kira-RAG · MCP", "sub": "Projektgedächtnis für Claude Code"},
    "flow-agent": {"title": "flow-agent", "sub": "Agent-Dienst"},
    "cockpit": {"title": "cockpit", "sub": "Diese Wand"},
    "rl_": {"title": "Rechnungslegung", "sub": "Seminar-Plattform"},
    "zvg": {"title": "ZVG", "sub": "Zwangsversteigerungen"},
    "pdfapp": {"title": "PDF-Editor", "sub": "pdf.flowaudit.de"},
    "ki-pilotprogramm": {"title": "KI-Pilotprogramm", "sub": "pilot.flowaudit.de"},
}

DEFAULT_HERO: dict[str, Any] = {
    "project": "hpp",
    "host": "ccx23",
    "title": "HPP · Preismonitoring-Portal",
    "sub": "Landeskartellbehörde Hessen · KPAnG-Vollzug",
    "url": "https://hpp.flowaudit.de",
    "demo_path": "/kraftstoff/vollzug/demo",
    "probe": "hpp",
}

# Sonden: JSON-Endpunkte, deren Felder als Kennzahlen erscheinen. Der
# Schluessel im Vault (secret_key) wird serverseitig als Header gesetzt.
DEFAULT_PROBES: list[dict[str, Any]] = [
    {
        "id": "hpp",
        "label": "HPP",
        "url": "https://hpp.flowaudit.de/api/kpang/vollzug/stats",
        "secret_key": "hpp_token",
        "header": "Authorization",
        "header_prefix": "Bearer ",
        "fields": [
            {"key": "preismeldungen_24h", "label": "Meldungen 24 h"},
            {"key": "tankstellen_aktiv", "label": "Tankstellen"},
            {"key": "verdachtsfaelle_24h", "label": "Verdachtsfälle 24 h"},
            {"key": "vorgaenge_offen", "label": "Verfahren offen"},
        ],
    },
]

# Projektverzeichnisse je Host fuer die Werkstatt (git-Stand, Pausen).
# Auf dem Self-Host ccx23 ist /home/deploy/Projekte nur lesend als /work/ccx23 eingehaengt.
DEFAULT_WORK_DIRS: dict[str, str] = {
    "ccx23": "/work/ccx23",
    "nuc": "/home/janpow/Projekte",
    "evo": "/home/janpow/Projekte",
}

# Kira-Memory: die API lauscht nur auf 127.0.0.1 des NUC; der Schluessel liegt
# dort in der .env und wird per SSH-Befehl gelesen, verlaesst den Host also nie.
DEFAULT_KIRA: dict[str, Any] = {
    "host": "nuc",
    "url": "http://127.0.0.1:8003/api/memory",
    "env_file": "/home/janpow/Projekte/audit_designer/.env",
    "env_key": "MEMORY_API_KEY",
}

DEFAULT_DEMO: dict[str, Any] = {
    "login_url": "https://hpp.flowaudit.de/api/auth/login",
    "aufbau_url": "https://hpp.flowaudit.de/api/kpang/vollzug/demo/aufbauen",
    "user_secret": "hpp_demo_user",
    "password_secret": "hpp_demo_password",
}

DEFAULT_MCP_SERVERS: list[dict[str, Any]] = [
    {
        "id": "flowaudit",
        "name": "flowaudit – Humanizer, Standards, Skills",
        "transport": "http",
        "url": "https://mcp.flowaudit.de/mcp",
        "secret_key": "mcp_flowaudit_token",
        "header": "Authorization",
        "header_prefix": "Bearer ",
        "skills_tool": "skills_list",
        "description": "Schreibstil, Terminologie, Standards der Prüfbehörde, Skill-Katalog – aus audit_designer.",
    },
    {
        "id": "memory",
        "name": "Kira-Memory (Projektgedächtnis)",
        "transport": "stdio",
        "command": "python backend/app/modules/memory/mcp_server.py (audit_designer, lokal in Claude Code)",
        "health_url": "https://mcp.flowaudit.de/health",
        "secret_key": "memory_api_key",
        "header": "X-Memory-API-Key",
        "header_prefix": "",
        "health_with_secret": False,
        "snippet": "claude mcp add memory -- python backend/app/modules/memory/mcp_server.py",
        "description": "RAG-Gedächtnis (Architektur, Lösungen, Referenzen) für Claude Code und Kira; Container checklist-mcp-memory auf ccx23.",
    },
]

# Whitelist der KI-Konsole: bewusst kurz. Der ai-router kennt viele weitere
# Modelle (flow-agent, EVO-Spokes) - die bleiben in der Konsole unsichtbar.
DEFAULT_CHAT_MODELS: list[dict[str, str]] = [
    {"tag": "qwen3.8-heretic:27b", "label": "Qwen 3.8 · 27B"},
    {"tag": "qwen3.5:35b-fast", "label": "Qwen 3.5 · 35B (schnell)"},
]

DEFAULT_CHAT_SYSTEM = (
    "Du bist die KI-Konsole des flowaudit-Cockpits. Antworte knapp, sachlich und auf Deutsch "
    "mit echten Umlauten. Wenn du etwas nicht weißt, sag es."
)


@dataclass
class WallConfig:
    hosts: list[str] = field(default_factory=list)
    hide: list[str] = field(default_factory=lambda: list(DEFAULT_HIDE))
    links: dict[str, str] = field(default_factory=lambda: dict(DEFAULT_LINKS))
    labels: dict[str, dict[str, str]] = field(default_factory=lambda: dict(DEFAULT_LABELS))
    hero: dict[str, Any] = field(default_factory=lambda: dict(DEFAULT_HERO))
    probes: list[dict[str, Any]] = field(default_factory=lambda: list(DEFAULT_PROBES))
    demo: dict[str, Any] = field(default_factory=lambda: dict(DEFAULT_DEMO))
    backup_dir: str = "/backups"
    chat_models: list[dict[str, str]] = field(default_factory=lambda: list(DEFAULT_CHAT_MODELS))
    chat_system: str = DEFAULT_CHAT_SYSTEM
    mcp_servers: list[dict[str, Any]] = field(default_factory=lambda: list(DEFAULT_MCP_SERVERS))
    work_dirs: dict[str, str] = field(default_factory=lambda: dict(DEFAULT_WORK_DIRS))
    kira: dict[str, Any] = field(default_factory=lambda: dict(DEFAULT_KIRA))

    def as_dict(self) -> dict[str, Any]:
        return {
            "hosts": self.hosts, "hide": self.hide, "links": self.links, "labels": self.labels,
            "hero": self.hero, "probes": self.probes, "demo": self.demo,
            "backup_dir": self.backup_dir, "chat_models": self.chat_models,
            "chat_system": self.chat_system,
            "mcp_servers": self.mcp_servers,
            "work_dirs": self.work_dirs, "kira": self.kira,
        }


_KEY = "wall"


def read_setting(session: Session, key: str, default: Any) -> Any:
    row = session.get(SettingRow, key)
    if row is None:
        return default
    try:
        return json.loads(row.value)
    except (json.JSONDecodeError, TypeError):
        return default


def write_setting(session: Session, key: str, value: Any) -> None:
    row = session.get(SettingRow, key)
    payload = json.dumps(value)
    if row is None:
        session.add(SettingRow(key=key, value=payload))
    else:
        row.value = payload
    session.commit()


def load(session: Session) -> WallConfig:
    raw = read_setting(session, _KEY, {}) or {}
    cfg = WallConfig()
    for name in ("hosts", "hide", "probes", "chat_models", "mcp_servers"):
        if isinstance(raw.get(name), list):
            setattr(cfg, name, raw[name])
    for name in ("links", "labels", "hero", "demo", "work_dirs", "kira"):
        if isinstance(raw.get(name), dict):
            setattr(cfg, name, raw[name])
    if isinstance(raw.get("backup_dir"), str) and raw["backup_dir"]:
        cfg.backup_dir = raw["backup_dir"]
    if isinstance(raw.get("chat_system"), str) and raw["chat_system"].strip():
        cfg.chat_system = raw["chat_system"]
    return cfg


def save(session: Session, patch: dict[str, Any]) -> WallConfig:
    """Teilweise Aktualisierung; unbekannte Schluessel werden ignoriert."""
    raw = read_setting(session, _KEY, {}) or {}
    for name in ("hosts", "hide", "probes", "chat_models", "mcp_servers"):
        if isinstance(patch.get(name), list):
            raw[name] = patch[name]
    for name in ("links", "labels", "hero", "demo", "work_dirs", "kira"):
        if isinstance(patch.get(name), dict):
            raw[name] = patch[name]
    for name in ("backup_dir", "chat_system"):
        if isinstance(patch.get(name), str):
            raw[name] = patch[name]
    write_setting(session, _KEY, raw)
    return load(session)


def is_hidden(name: str, hide: list[str]) -> bool:
    """Teilstring-Vergleich ohne Gross-/Kleinschreibung (rein, testbar)."""
    n = (name or "").lower()
    return any(h and h.lower() in n for h in hide)


def link_for(name: str, container_names: list[str], links: dict[str, str]) -> str | None:
    """Oeffentliche Adresse: Projektname exakt, sonst Container-Praefix (rein, testbar)."""
    if name in links:
        return links[name]
    for key, url in links.items():
        if any(c.startswith(key) for c in container_names):
            return url
    return None


def label_for(name: str, container_names: list[str], labels: dict[str, dict[str, str]]) -> dict[str, str]:
    if name in labels:
        return labels[name]
    for key, lab in labels.items():
        if any(c.startswith(key) for c in container_names):
            return lab
    return {"title": name, "sub": ""}
