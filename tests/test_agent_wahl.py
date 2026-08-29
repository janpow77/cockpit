"""Automatische Agentenwahl (rein)."""

from cockpit.services import agent_wahl as aw

ALLE = {"claude": True, "codex": True, "gemini": True}


def test_aufgabentyp():
    assert aw.aufgabentyp("Repo prüfen: x", "Prüfe …", "bericht", "lesen") == "bericht"
    assert aw.aufgabentyp("Icons vereinheitlichen: x", "…", "plan_freigabe", "bearbeiten_tests") == "oberflaeche"
    assert aw.aufgabentyp("Fehler beheben: x", "Bug im Import", "umsetzen", "bearbeiten_tests") == "umsetzung"
    assert aw.aufgabentyp("Migration für Oberfläche", "…", "umsetzen", "bearbeiten") == "umsetzung"


def test_wahl_nach_typ_und_kontingent():
    assert aw.waehlen("bericht", claude_5h=10, claude_woche=50, codex_woche=2, verfuegbar=ALLE)[0] == "codex"
    assert aw.waehlen("umsetzung", claude_5h=10, claude_woche=50, codex_woche=2, verfuegbar=ALLE)[0] == "claude"
    assert aw.waehlen("umsetzung", claude_5h=90, claude_woche=50, codex_woche=2, verfuegbar=ALLE)[0] == "codex"
    assert aw.waehlen("oberflaeche", claude_5h=10, claude_woche=50, codex_woche=2, verfuegbar=ALLE)[0] == "gemini"
    assert aw.waehlen("oberflaeche", claude_5h=10, claude_woche=50, codex_woche=2, verfuegbar={"claude": True, "codex": True})[0] == "codex"
    assert aw.waehlen("bericht", claude_5h=10, claude_woche=50, codex_woche=99, verfuegbar=ALLE)[0] == "gemini"
    # Claude und Codex ausgeschöpft → agy (eigenes Kontingent, nicht messbar) als letzter Ausweich
    assert aw.waehlen("umsetzung", claude_5h=99, claude_woche=99, codex_woche=99, verfuegbar=ALLE)[0] == "gemini"
    agent, grund = aw.waehlen("umsetzung", claude_5h=99, claude_woche=99, codex_woche=99, verfuegbar={"claude": True, "codex": True})
    assert agent == "claude" and "knapp" in grund
    assert aw.waehlen("umsetzung", claude_5h=None, claude_woche=None, codex_woche=None, verfuegbar={})[0] == "claude"
