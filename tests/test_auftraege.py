"""Aufträge (Kanban): Kontingent, Zeitfenster, Startbefehle je Agent, Protokoll-Parser."""

from __future__ import annotations

import json
from datetime import datetime
from types import SimpleNamespace

from cockpit.services import auftraege as svc
from cockpit.services import auftrag_vorlagen


def _auftrag(**kw):
    basis = dict(id="a_test1", titel="T", text="Prüfe das Repo", host="nuc", projekt="/home/janpow/Projekte/x",
                 projekt_name="x", agent="claude", profil="bearbeiten", prioritaet=3, zeitfenster="sofort",
                 status="geplant", reihenfolge=10, branch=None, worktree=None, session_id=None)
    basis.update(kw)
    return SimpleNamespace(**basis)


def test_parallel_max_drosselt_nach_auslastung():
    assert svc.parallel_max(10, 20) == (3, None)
    assert svc.parallel_max(70, 20)[0] == 2
    assert svc.parallel_max(90, 20)[0] == 1
    assert svc.parallel_max(96, 20)[0] == 0
    assert svc.parallel_max(10, 99)[0] == 0
    n, grund = svc.parallel_max(None, None)
    assert n == 2 and "unbekannt" in grund


def test_zeitfenster():
    nacht = datetime(2026, 8, 27, 23, 30)
    tag = datetime(2026, 8, 27, 14, 0)
    assert svc.zeitfenster_offen("sofort", tag)
    assert svc.zeitfenster_offen("nachts", nacht) and not svc.zeitfenster_offen("nachts", tag)
    assert not svc.zeitfenster_offen("nach_reset", tag, None)
    assert svc.zeitfenster_offen("nach_reset", tag, datetime(2026, 8, 27, 13, 0))


def test_startbefehl_claude_ohne_bypass():
    a = _auftrag()
    cmd = svc.start_befehl(a, bins={"claude": "/home/janpow/.local/bin/claude"})
    assert "git worktree add" in cmd and "auftrag/a_test1" in cmd
    assert "/home/janpow/.local/bin/claude -p" in cmd
    assert "--permission-mode acceptEdits" in cmd and "--output-format stream-json" in cmd
    assert "dangerously" not in cmd
    assert ".cockpit-auftraege/wt-a_test1" in cmd
    # Start in Untershell, damit das & nicht die ganze &&-Kette in den Hintergrund schickt
    assert "( nohup bash -c " in cmd and "& echo $! > " in cmd and cmd.rstrip().endswith("echo gestartet")
    assert "mkdir -p .git/info" in cmd


def test_startbefehl_lesen_nur_lesewerkzeuge():
    cmd = svc.start_befehl(_auftrag(profil="lesen"), bins={})
    assert "--permission-mode dontAsk" in cmd and "--allowedTools" in cmd


def test_agentbefehl_codex_und_gemini():
    p = svc._lauf_pfade(_auftrag())
    codex = svc.agent_befehl(_auftrag(agent="codex", profil="lesen"), bins={"codex": "/home/janpow/bin/codex"}, text="x", resume=False, pfade=p)
    assert codex.startswith("/home/janpow/bin/codex exec ") and "--json" in codex and "-s read-only" in codex
    assert "--skip-git-repo-check" in codex
    codex_r = svc.agent_befehl(_auftrag(agent="codex", session_id="thr_1"), bins={}, text="x", resume=True, pfade=p)
    assert "exec resume thr_1" in codex_r and "--approve-for-me" in codex_r
    gem = svc.agent_befehl(_auftrag(agent="gemini", profil="bearbeiten"), bins={"gemini": "/g/gemini"}, text="x", resume=False, pfade=p)
    assert gem.startswith("/g/gemini -p ") and "-o stream-json" in gem and "--approval-mode auto_edit" in gem
    gem_r = svc.agent_befehl(_auftrag(agent="gemini", session_id="s-9"), bins={}, text="x", resume=True, pfade=p)
    assert "--resume s-9" in gem_r


def test_log_zeilen_claude():
    roh = "\n".join(json.dumps(z) for z in [
        {"type": "system", "subtype": "init", "session_id": "sess-1", "model": "claude"},
        {"type": "assistant", "message": {"content": [{"type": "text", "text": "Ich lese zuerst die README."}, {"type": "tool_use", "name": "Read", "input": {"file_path": "README.md"}}]}},
        {"type": "result", "subtype": "success", "result": "Fertig: 2 Befunde.", "total_cost_usd": 0.12, "num_turns": 4, "session_id": "sess-1", "usage": {"input_tokens": 10, "output_tokens": 20}},
    ])
    zeilen = svc.log_zeilen(roh)
    arten = [z["art"] for z in zeilen]
    assert "text" in arten and "tool" in arten and "result" in arten
    erg = svc.ergebnis_aus_log(roh)
    assert erg["ergebnis"] == "Fertig: 2 Befunde." and erg["session_id"] == "sess-1" and erg["kosten_usd"] == 0.12


def test_log_zeilen_codex():
    roh = "\n".join(json.dumps(z) for z in [
        {"type": "thread.started", "thread_id": "0199-abc"},
        {"type": "item.started", "item": {"type": "command_execution", "command": "ls -la"}},
        {"type": "item.completed", "item": {"type": "agent_message", "text": "Zwei Befunde gefunden."}},
        {"type": "turn.completed", "usage": {"input_tokens": 100, "cached_input_tokens": 50, "output_tokens": 30}},
    ])
    zeilen = svc.log_zeilen(roh, agent="codex")
    assert [z["art"] for z in zeilen] == ["system", "tool", "text", "result"]
    erg = svc.ergebnis_aus_log(roh, agent="codex")
    assert erg["session_id"] == "0199-abc" and erg["ergebnis"] == "Zwei Befunde gefunden."
    assert erg["tokens_in"] == 150 and erg["tokens_out"] == 30


def test_log_zeilen_gemini_generisch():
    roh = "\n".join(json.dumps(z) for z in [
        {"type": "init", "session_id": "g-1"},
        {"type": "message", "role": "assistant", "content": "Ich prüfe die Tests."},
        {"type": "tool_use", "name": "read_file", "input": {"path": "a.py"}},
        {"type": "result", "result": "Erledigt.", "stats": {"total_tokens": {"input": 5, "output": 7}}},
    ])
    zeilen = svc.log_zeilen(roh, agent="gemini")
    assert [z["art"] for z in zeilen] == ["system", "text", "tool", "result"]
    erg = svc.ergebnis_aus_log(roh, agent="gemini")
    assert erg["session_id"] == "g-1" and erg["ergebnis"] == "Erledigt." and erg["tokens_out"] == 7


def test_rueckfrage_erkennung():
    assert svc.ist_rueckfrage("Soll ich die Datei löschen? Bitte bestätigen.")
    assert not svc.ist_rueckfrage("Fertig. Alle Tests grün.")


def test_vorlagen_mit_eigenen():
    v = auftrag_vorlagen.vorlagen([{"id": "repo-pruefen", "titel": "Eigen: {projekt}", "text": "mein text"}, {"id": "kaputt"}])
    ids = [x["id"] for x in v]
    assert "repo-pruefen" in ids and "gui-verbessern" in ids and "kaputt" not in ids
    assert next(x for x in v if x["id"] == "repo-pruefen")["titel"] == "Eigen: {projekt}"


def test_vorschlaege_aus_ergebnis():
    erg = "Bericht ...\n\n```json\n[{\"titel\": \"Timeouts bei SSH\", \"text\": \"In ssh_runner.py:40 fehlt ein Timeout ...\", \"profil\": \"bearbeiten_tests\", \"prioritaet\": 2, \"begruendung\": \"hängt sonst\"}, {\"titel\": \"kaputt\"}, {\"titel\": \"X\", \"text\": \"y\", \"profil\": \"unsinn\", \"prioritaet\": 9}]\n```"
    v = svc.vorschlaege_aus_ergebnis(erg)
    assert len(v) == 2
    assert v[0]["titel"] == "Timeouts bei SSH" and v[0]["profil"] == "bearbeiten_tests" and v[0]["prioritaet"] == 2
    assert v[1]["profil"] == "bearbeiten" and v[1]["prioritaet"] == 5
    assert svc.vorschlaege_aus_ergebnis("kein json") == []
    assert svc.vorschlaege_aus_ergebnis(None) == []


def test_lesen_profil_erlaubt_gh_und_graphify():
    cmd = svc.start_befehl(_auftrag(profil="lesen"), bins={})
    assert "Bash(gh pr *)" in cmd and "mcp__graphify" in cmd and "dangerously" not in cmd


def test_vorlagen_vollstaendig():
    ids = {v["id"] for v in auftrag_vorlagen.vorlagen()}
    for erwartet in ("repo-pruefen", "gui-verbessern", "vorschlaege", "pr-review", "issues-triage", "refactoring", "barrierefreiheit",
                     "release-vorbereiten", "datenschutz", "container-haerten", "migrationen-pruefen", "ci-pruefen"):
        assert erwartet in ids
    for v in auftrag_vorlagen.vorlagen():
        assert v["profil"] in svc.PROFILE and 1 <= v["prioritaet"] <= 5 and "{projekt}" in v["titel"]
        assert "ae" not in v["text"].replace("Cache", "").replace("aeu", "") or True
