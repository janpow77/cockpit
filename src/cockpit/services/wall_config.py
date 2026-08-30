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
    "kira_cloudflared",  # Kira-Tunnel (kiraclaw/deploy), bewusst gestoppt
]

# Produktionshosts: nur dort loesen gestoppte/teilweise Projekte mit Registrierung oder
# oeffentlicher Adresse einen Alarm aus (unabhaengig davon, auf welchem Host die Wand laeuft).
DEFAULT_PROD_HOSTS: list[str] = ["ccx23"]

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
    "kira_": {"title": "Kira · Tunnel", "sub": "kiraclaw/deploy · Cloudflare"},
}

DEFAULT_HERO: dict[str, Any] = {
    "project": "hpp",
    "host": "ccx23",
    "title": "HPP · Preismonitoring-Portal",
    "sub": "Landeskartellbehörde Hessen · KPAnG-Vollzug",
    "url": "https://hpp.flowaudit.de",
    # Nach dem Aufbau oeffnet das Board die Demo-Uebersicht des HPP: sie zeigt
    # die aufgebauten Faelle mit Stand und Direktlinks in die Akten und
    # daneben die gefuehrte Tour. Vorher stand hier "/kraftstoff/vollzug" -
    # damit landete der Klick auf "Demo starten" auf "Moegliche Verstoesse",
    # also gerade nicht bei dem, was soeben aufgebaut wurde.
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
        "login_url": "https://hpp.flowaudit.de/api/auth/login",
        "user_secret": "hpp_smoke_user",
        "password_secret": "hpp_smoke_password",
        "fields": [
            {"key": "preismeldungen_24h", "label": "Meldungen 24 h"},
            {"key": "tankstellen_aktiv", "label": "Tankstellen"},
            {"key": "verdachtsfaelle_24h", "label": "Verdachtsfälle 24 h"},
            {"key": "vorgaenge_offen", "label": "Verfahren offen"},
        ],
    },
]

# Projektverzeichnisse je Host fuer die Werkstatt (git-Stand, Pausen). Der jeweilige
# Self-Host bindet sein Verzeichnis unter demselben Pfad nur lesend in den Container ein,
# damit dieselbe Vorgabe fuer jede Instanz (Hetzner, NUC, janpow-ai) gilt.
DEFAULT_WORK_DIRS: dict[str, str] = {
    "ccx23": "/home/deploy/Projekte",
    "nuc": "/home/janpow/Projekte",
    "evo": "/home/janpow/Projekte",
    "janpow-ai": "/home/janpow/Projekte",
}

# Kira-Memory: die API lauscht nur auf 127.0.0.1 des NUC; der Schluessel liegt
# dort in der .env und wird per SSH-Befehl gelesen, verlaesst den Host also nie.
DEFAULT_KIRA: dict[str, Any] = {
    "host": "nuc",
    "url": "http://127.0.0.1:8003/api/memory",
    "env_file": "/home/janpow/Projekte/audit_designer/.env",
    "env_key": "MEMORY_API_KEY",
}

# Push-Alarme per Telegram (Bot-Token und Chat-ID im Vault). Nachts nur Kritisches.
DEFAULT_PUSH: dict[str, Any] = {
    # Telegram-Dialog (Schaltflächen, Antworten per Reply, Kommandos) – nur auf der Instanz mit aktivem Push
    "dialog": {"aktiv": True, "erlaubte_user_ids": [], "kuerzen": True, "token_secret": ""},  # token_secret leer = Push-Bot; sonst eigener Cockpit-Bot (Vault)
    "aktiv": True,
    "kanal": "telegram",
    "token_secret": "telegram_bot_token",
    "chat_secret": "telegram_chat_id",
    "min_level": "warn",
    "ruhe_von": "22:00",
    "ruhe_bis": "07:00",
    "zeitzone": "Europe/Berlin",
    "instanz": "",
    "wand_url": "http://100.99.159.80:7843/admin/board",
}

# KI-Nutzung: Auslastung/Limits von Claude Code und Codex vom Arbeitsplatz-Host (NUC)
DEFAULT_KI_NUTZUNG: dict[str, Any] = {
    "host": "nuc",
    "claude_credentials": "/home/janpow/.claude/.credentials.json",
    "claude_projekte": "/home/janpow/.claude/projects",
    "codex_sessions": "/home/janpow/.codex/sessions",
    "warn_pct": 85,
}

# Aufträge (Kanban): Agenten-Programme auf dem Arbeitsplatz-Host, Parallelität, eigene Vorlagen
DEFAULT_AGENT_BINS: dict[str, str] = {
    "claude": "/home/janpow/.local/bin/claude",
    "codex": "/home/janpow/bin/codex",
    "gemini": "/home/janpow/.npm-global/bin/gemini",
}

# Vorschlagsläufe gibt es nur noch auf Anstoß von Hand: über die Kanban-Vorlage oder das
# Telegram-Kommando /vorschlaege. Der Runner plant nichts mehr selbst und legt aus den
# Ergebnissen auch keine Karten mehr an (siehe auftrag_runner.runde()). wochentag, stunde und
# max_je_woche bleiben nur als Felder des Vertrags erhalten; sie steuern nichts mehr.
DEFAULT_VORSCHLAEGE: dict[str, Any] = {"aktiv": False, "wochentag": 6, "stunde": 1, "agent": "codex", "max_je_woche": 8}

# flow-agent (agent.flowaudit.de): Projektinventar/graphify je Host, Lese-Schlüssel im Vault; hosts = flow-agent-Hostname → Cockpit-Host
DEFAULT_FLOW_AGENT: dict[str, Any] = {
    "url": "https://agent.flowaudit.de", "secret_key": "flow_agent_read_key",
    "hosts": {"janpow-NUC15JNLU7X4": "nuc", "cockpit-nbg1-1": "ccx23", "evo2": "evo", "MacBook-Air.local": "macbook", "janpow-ai": "janpow-ai"},
    # Woher die Host-Kennzahlen kommen: "auto" = flow-agent, wenn die eigene SSH-Sonde nichts liefert;
    # "flow-agent" = immer von dort (keine eigene SSH-Last); "ssh" = wie bisher nur eigene Sonde.
    "quelle_hosts": "auto",
}

# Leitinstanz: url leer = diese Instanz führt Aufträge selbst; sonst werden /admin/api/auftraege dorthin durchgereicht
DEFAULT_LEITINSTANZ: dict[str, Any] = {"url": "", "benutzer_secret": "leitinstanz_benutzer", "passwort_secret": "leitinstanz_passwort"}

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
    "Du bist die LLM-Konsole des flowaudit-Cockpits von Jan Riener (Prüfbehörde EFRE Hessen, "
    "Entwickler von HPP, Checklisten-Designer, flowinvoice u. a.). Antworte sachlich und auf Deutsch mit echten "
    "Umlauten – so knapp wie möglich: kurze Fragen in zwei bis vier Sätzen ohne Überschriften, Listen nur bei "
    "Aufzählungen. Stütze dich auf den mitgelieferten Kira-Kontext und zitiere ihn als [n]; "
    "fehlt Passendes, sag es, statt zu raten. "
    "Glossar: HPP = Hessisches Preismonitoring-Portal (Landeskartellbehörde Hessen); "
    "KPAnG = Kraftstoffpreisanpassungsgesetz (12-Uhr-Regel: Preiserhöhungen nur einmal täglich um 12 Uhr, "
    "Toleranzfenster 12:00–12:06); MTS-K = Markttransparenzstelle für Kraftstoffe; "
    "VerwK = Verwaltungskontrolle (Art. 74 CPR), Feststellungen (formell/finanziell), "
    "TER = Gesamtfehlerquote, RER = Restfehlerquote; Kira = Projektgedächtnis (RAG); "
    "Checklisten-Designer = audit_designer (EFRE-Vorhabenprüfung)."
)

# Kontextfenster des Modells, wenn RAG-Kontext mitgegeben wird (Ollama num_ctx)
DEFAULT_CHAT_NUM_CTX = 12288
# Denkmodus (Qwen "thinking"): aus - sonst dauert jede Antwort Minuten (2.700 versteckte Tokens gemessen)
DEFAULT_CHAT_THINK = False


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
    chat_num_ctx: int = DEFAULT_CHAT_NUM_CTX
    chat_think: bool = DEFAULT_CHAT_THINK
    mcp_servers: list[dict[str, Any]] = field(default_factory=lambda: list(DEFAULT_MCP_SERVERS))
    work_dirs: dict[str, str] = field(default_factory=lambda: dict(DEFAULT_WORK_DIRS))
    kira: dict[str, Any] = field(default_factory=lambda: dict(DEFAULT_KIRA))
    prod_hosts: list[str] = field(default_factory=lambda: list(DEFAULT_PROD_HOSTS))
    push: dict[str, Any] = field(default_factory=lambda: dict(DEFAULT_PUSH))
    ki_nutzung: dict[str, Any] = field(default_factory=lambda: dict(DEFAULT_KI_NUTZUNG))
    agent_bins: dict[str, str] = field(default_factory=lambda: dict(DEFAULT_AGENT_BINS))
    vorschlaege: dict[str, Any] = field(default_factory=lambda: dict(DEFAULT_VORSCHLAEGE))
    flow_agent: dict[str, Any] = field(default_factory=lambda: dict(DEFAULT_FLOW_AGENT))
    leitinstanz: dict[str, Any] = field(default_factory=lambda: dict(DEFAULT_LEITINSTANZ))
    auftrag_vorlagen: list[dict[str, Any]] = field(default_factory=list)
    auftrag_parallel: int = 3
    codex_sandbox: str = "danger-full-access"  # bubblewrap auf dem NUC nicht nutzbar; "workspace-write" wo es geht
    agent_hosts: list[str] = field(default_factory=lambda: ["nuc"])  # Hosts, auf denen claude/codex/agy angemeldet sind
    auftrag_max_dauer_min: int = 90  # danach gilt ein Lauf als unterbrochen (Fortsetzen möglich)
    auftrag_aufraeumen_tage: int = 14  # Worktrees fertiger/abgebrochener Aufträge nach so vielen Tagen entfernen
    werkstatt_aktiv_tage: int = 14
    verlauf_tage: int = 30
    chat_max_tokens: int = 900

    def as_dict(self) -> dict[str, Any]:
        return {
            "hosts": self.hosts, "hide": self.hide, "links": self.links, "labels": self.labels,
            "hero": self.hero, "probes": self.probes, "demo": self.demo,
            "backup_dir": self.backup_dir, "chat_models": self.chat_models,
            "chat_system": self.chat_system,
            "chat_num_ctx": self.chat_num_ctx,
            "chat_think": self.chat_think,
            "mcp_servers": self.mcp_servers,
            "work_dirs": self.work_dirs, "kira": self.kira, "prod_hosts": self.prod_hosts,
            "push": self.push, "ki_nutzung": self.ki_nutzung, "werkstatt_aktiv_tage": self.werkstatt_aktiv_tage,
            "agent_bins": self.agent_bins, "auftrag_vorlagen": self.auftrag_vorlagen, "auftrag_parallel": self.auftrag_parallel, "vorschlaege": self.vorschlaege, "flow_agent": self.flow_agent, "leitinstanz": self.leitinstanz, "codex_sandbox": self.codex_sandbox, "agent_hosts": self.agent_hosts,
            "auftrag_max_dauer_min": self.auftrag_max_dauer_min, "auftrag_aufraeumen_tage": self.auftrag_aufraeumen_tage,
            "verlauf_tage": self.verlauf_tage, "chat_max_tokens": self.chat_max_tokens,
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
    for name in ("hosts", "hide", "probes", "chat_models", "mcp_servers", "prod_hosts"):
        if isinstance(raw.get(name), list):
            setattr(cfg, name, raw[name])
    for name in ("links", "labels", "hero", "demo", "work_dirs", "kira", "push", "ki_nutzung", "agent_bins", "vorschlaege", "flow_agent", "leitinstanz"):
        if isinstance(raw.get(name), dict):
            setattr(cfg, name, raw[name])
    if isinstance(raw.get("auftrag_vorlagen"), list):
        cfg.auftrag_vorlagen = raw["auftrag_vorlagen"]
    if raw.get("codex_sandbox") in ("danger-full-access", "workspace-write"):
        cfg.codex_sandbox = str(raw["codex_sandbox"])
    if isinstance(raw.get("agent_hosts"), list):
        cfg.agent_hosts = [str(h) for h in raw["agent_hosts"] if h]
    for name, lo, hi in (("werkstatt_aktiv_tage", 1, 365), ("verlauf_tage", 1, 365), ("chat_max_tokens", 100, 8000), ("auftrag_parallel", 1, 8), ("auftrag_max_dauer_min", 5, 1440), ("auftrag_aufraeumen_tage", 1, 365)):
        if isinstance(raw.get(name), int) and lo <= raw[name] <= hi:
            setattr(cfg, name, raw[name])
    if isinstance(raw.get("backup_dir"), str) and raw["backup_dir"]:
        cfg.backup_dir = raw["backup_dir"]
    if isinstance(raw.get("chat_system"), str) and raw["chat_system"].strip():
        cfg.chat_system = raw["chat_system"]
    if isinstance(raw.get("chat_num_ctx"), int) and 2048 <= raw["chat_num_ctx"] <= 131072:
        cfg.chat_num_ctx = raw["chat_num_ctx"]
    if isinstance(raw.get("chat_think"), bool):
        cfg.chat_think = raw["chat_think"]
    return cfg


def save(session: Session, patch: dict[str, Any]) -> WallConfig:
    """Teilweise Aktualisierung; unbekannte Schluessel werden ignoriert."""
    raw = read_setting(session, _KEY, {}) or {}
    for name in ("hosts", "hide", "probes", "chat_models", "mcp_servers", "prod_hosts"):
        if isinstance(patch.get(name), list):
            raw[name] = patch[name]
    for name in ("links", "labels", "hero", "demo", "work_dirs", "kira", "push", "ki_nutzung", "agent_bins", "vorschlaege", "flow_agent", "leitinstanz"):
        if isinstance(patch.get(name), dict):
            raw[name] = patch[name]
    if isinstance(patch.get("auftrag_vorlagen"), list):
        raw["auftrag_vorlagen"] = patch["auftrag_vorlagen"]
    if patch.get("codex_sandbox") in ("danger-full-access", "workspace-write"):
        raw["codex_sandbox"] = patch["codex_sandbox"]
    if isinstance(patch.get("agent_hosts"), list):
        raw["agent_hosts"] = [str(h) for h in patch["agent_hosts"] if h]
    for name in ("werkstatt_aktiv_tage", "verlauf_tage", "chat_max_tokens", "auftrag_parallel", "auftrag_max_dauer_min", "auftrag_aufraeumen_tage"):
        if isinstance(patch.get(name), int):
            raw[name] = patch[name]
    for name in ("backup_dir", "chat_system"):
        if isinstance(patch.get(name), str):
            raw[name] = patch[name]
    if isinstance(patch.get("chat_num_ctx"), int):
        raw["chat_num_ctx"] = patch["chat_num_ctx"]
    if isinstance(patch.get("chat_think"), bool):
        raw["chat_think"] = patch["chat_think"]
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
