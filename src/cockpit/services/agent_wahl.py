"""Automatische Agentenwahl je Auftrag: Aufgabentyp und verbleibende Kontingente entscheiden (rein, testbar).

Regel (Konzept, Arbeitspaket D):
  Bericht / Audit / Vorschläge (lesend)      → Codex, sonst agy, sonst Claude  – schont das Claude-5-Stunden-Fenster
  Umsetzung mit Tests, Refactoring, Fehler   → Claude, bei ≥ 85 % Auslastung Codex
  Oberfläche, Icons, Übersetzen, Doku        → agy, sonst Codex
  Nachfrage / Fortsetzung                    → immer derselbe Agent (Sitzung bleibt)
Ein Agent gilt als verfügbar, wenn sein Programm eingetragen ist; Claude zusätzlich nur unterhalb
der Auslastungsgrenzen, Codex unterhalb seines Wochenlimits.
"""

from __future__ import annotations

UI_WOERTER = ("oberfläche", "icon", "übersetz", "sprache", "doku", "readme", "farben", "typografie", "barrierefrei", "mobil", "formular", "tabelle", "design")
KOMPLEX_WOERTER = ("refactor", "entflecht", "fehler beheb", "bug", "migration", "performance", "test", "tests ergänz", "architektur", "sicherheit", "api")


def aufgabentyp(titel: str, text: str, modus: str, profil: str) -> str:
    """'bericht' | 'oberflaeche' | 'umsetzung' aus Modus, Profil und Stichworten."""
    if modus == "bericht" or profil == "lesen":
        return "bericht"
    t = f"{titel} {text}".lower()
    if any(w in t for w in UI_WOERTER) and not any(w in t for w in ("migration", "sicherheit", "refactor")):
        return "oberflaeche"
    return "umsetzung"


def waehlen(typ: str, *, claude_5h: float | None, claude_woche: float | None, codex_woche: float | None,
            verfuegbar: dict[str, bool], grenze_claude: float = 85.0) -> tuple[str, str]:
    """(agent, begründung). `verfuegbar` = {claude, codex, gemini: bool} aus agent_bins/Anmeldung."""
    claude_ok = verfuegbar.get("claude", False) and (claude_5h is None or claude_5h < grenze_claude) and (claude_woche is None or claude_woche < 95)
    codex_ok = verfuegbar.get("codex", False) and (codex_woche is None or codex_woche < 95)
    agy_ok = verfuegbar.get("gemini", False)
    if typ == "bericht":
        reihe = [("codex", codex_ok, "lesende Aufgabe – Codex schont das Claude-Fenster"), ("gemini", agy_ok, "lesende Aufgabe – agy, Codex-Kontingent knapp"), ("claude", claude_ok, "lesende Aufgabe – nur Claude verfügbar")]
    elif typ == "oberflaeche":
        reihe = [("gemini", agy_ok, "Oberfläche/Sprache – agy mit eigenem Kontingent"), ("codex", codex_ok, "Oberfläche – Codex, agy nicht verfügbar"), ("claude", claude_ok, "Oberfläche – Claude als Ausweich")]
    else:
        reihe = [("claude", claude_ok, "Umsetzung – Claude mit CLAUDE.md-Konventionen"), ("codex", codex_ok, f"Umsetzung – Codex, Claude-Auslastung ≥ {int(grenze_claude)} % oder nicht verfügbar"), ("gemini", agy_ok, "Umsetzung – agy als letzter Ausweich")]
    for agent, ok, grund in reihe:
        if ok:
            return agent, grund
    # alles ausgeschöpft: erster verfügbarer, sonst Claude (wartet dann im Kontingent)
    for agent in ("claude", "codex", "gemini"):
        if verfuegbar.get(agent):
            return agent, "alle Kontingente knapp – wartet im Kontingent"
    return "claude", "kein Agent eingetragen – Claude als Vorgabe"
