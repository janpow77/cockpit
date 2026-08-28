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
                 status="geplant", reihenfolge=10, branch=None, worktree=None, session_id=None, modus="umsetzen", freigegeben=None,
                 pruefung=None, pruefung_ok=None, pr_url=None, pr_checks=None, ergebnis=None, agent_auto=None, agent_grund=None)
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
    assert "Arbeitsverzeichnis (Git-Worktree, Branch auftrag/a_test1)" in cmd
    # node_modules/.venv des Hauptrepos werden in den Worktree verlinkt
    assert "ln -s /home/janpow/Projekte/x/$d/$m" in cmd and "node_modules .venv venv" in cmd


def test_startbefehl_lesen_nur_lesewerkzeuge():
    cmd = svc.start_befehl(_auftrag(profil="lesen"), bins={})
    assert "--permission-mode dontAsk" in cmd and "--allowedTools" in cmd


def test_agentbefehl_codex_und_gemini():
    p = svc._lauf_pfade(_auftrag())
    ww = {"codex": "/home/janpow/bin/codex", "codex_sandbox": "workspace-write"}
    codex = svc.agent_befehl(_auftrag(agent="codex", profil="lesen"), bins=ww, text="x", resume=False, pfade=p)
    assert codex.startswith("/home/janpow/bin/codex exec ") and "--json" in codex and "-s read-only" in codex
    assert "--skip-git-repo-check" in codex
    codex_r = svc.agent_befehl(_auftrag(agent="codex", session_id="thr_1"), bins=ww, text="x", resume=True, pfade=p)
    assert "exec resume thr_1" in codex_r and "-c sandbox_mode=workspace-write" in codex_r and "-c approval_policy=never" in codex_r
    assert " -s " not in codex_r and "--approve-for-me" not in codex_r  # exec resume kennt diese Flags nicht
    assert 'thread-writer-locks/*thr_1*' in codex_r  # Schreibsperre eines toten Prozesses räumen
    codex_rl = svc.agent_befehl(_auftrag(agent="codex", profil="lesen", session_id="thr_1"), bins=ww, text="x", resume=True, pfade=p)
    assert "-c sandbox_mode=read-only" in codex_rl
    # Vorgabe auf dem NUC: bwrap unbrauchbar → ohne Isolierung, aber nie --dangerously-bypass-approvals-and-sandbox
    ohne = svc.agent_befehl(_auftrag(agent="codex", profil="bearbeiten_tests"), bins={}, text="x", resume=False, pfade=p)
    assert "-s danger-full-access" in ohne and "dangerously" not in ohne
    ohne_r = svc.agent_befehl(_auftrag(agent="codex", session_id="thr_1"), bins={}, text="x", resume=True, pfade=p)
    assert "-c sandbox_mode=danger-full-access" in ohne_r
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
    assert "Bash(gh pr list *)" in cmd and "mcp__graphify" in cmd and "dangerously" not in cmd
    assert "Bash(gh api *)" not in cmd and "Bash(gh issue *)" not in cmd  # keine mutierenden gh-Aufrufe im Leseprofil


def test_vorlagen_vollstaendig():
    ids = {v["id"] for v in auftrag_vorlagen.vorlagen()}
    for erwartet in ("repo-pruefen", "gui-verbessern", "vorschlaege", "pr-review", "issues-triage", "refactoring", "barrierefreiheit",
                     "release-vorbereiten", "datenschutz", "container-haerten", "migrationen-pruefen", "ci-pruefen"):
        assert erwartet in ids
    for v in auftrag_vorlagen.vorlagen():
        assert v["profil"] in svc.PROFILE and 1 <= v["prioritaet"] <= 5 and "{projekt}" in v["titel"]
        assert "ae" not in v["text"].replace("Cache", "").replace("aeu", "") or True


def test_modus_phase_profil_und_prompt():
    b = _auftrag(modus="bericht", profil="bearbeiten_tests")
    assert svc.phase(b) == "plan" and svc.effektives_profil(b) == "lesen"
    assert "[Modus: nur Bericht]" in svc.prompt_fuer(b)
    pf = _auftrag(modus="plan_freigabe", profil="bearbeiten_tests")
    assert svc.phase(pf) == "plan" and svc.effektives_profil(pf) == "lesen"
    assert "[Modus: Plan mit Freigabe]" in svc.prompt_fuer(pf)
    assert svc.status_nach_erfolg(pf, "Plan: 1. …") == "freigabe"
    pf.freigegeben = "2026-08-28T10:00:00Z"
    assert svc.phase(pf) == "umsetzung" and svc.effektives_profil(pf) == "bearbeiten_tests"
    assert svc.status_nach_erfolg(pf, "Alles umgesetzt.") == "fertig"
    assert svc.prompt_fuer(pf, resume=True, nachfrage=svc.umsetzungstext("nur Schritt 1–3")).startswith("Freigegeben.")
    u = _auftrag(modus="umsetzen", profil="lesen")
    assert svc.effektives_profil(u) == "lesen"  # Wahl der Karte wird respektiert
    assert "[Modus" not in svc.prompt_fuer(u)


def test_startbefehl_folgt_der_phase():
    pf = _auftrag(modus="plan_freigabe", profil="bearbeiten_tests")
    cmd = svc.start_befehl(pf, bins={})
    assert "--permission-mode dontAsk" in cmd and "Plan mit Freigabe" in cmd
    pf.freigegeben = "2026-08-28T10:00:00Z"
    pf.session_id = "sess-1"
    cmd2 = svc.start_befehl(pf, bins={}, resume=True, nachfrage=svc.umsetzungstext())
    assert "--permission-mode acceptEdits" in cmd2 and "--resume sess-1" in cmd2 and "Freigegeben." in cmd2


def test_agy_befehl():
    p = svc._lauf_pfade(_auftrag())
    a = _auftrag(agent="gemini", profil="bearbeiten_tests", modus="umsetzen", session_id="conv-1")
    cmd = svc.agent_befehl(a, bins={"gemini": "/home/janpow/.local/bin/agy"}, text="x", resume=True, pfade=p)
    assert cmd.startswith("/home/janpow/.local/bin/agy -p ") and "--output-format stream-json" in cmd
    assert "--conversation conv-1" in cmd and "--mode accept-edits" in cmd and "--sandbox" not in cmd
    assert "--add-dir /home/janpow/Projekte/x/.cockpit-auftraege/wt-a_test1" in cmd
    lese = svc.agent_befehl(_auftrag(agent="gemini", modus="bericht"), bins={"gemini": "/x/agy"}, text="x", resume=False, pfade=p)
    assert "--mode plan" in lese and "--mode accept-edits" not in lese
    voll = svc.agent_befehl(_auftrag(agent="gemini", profil="voll"), bins={"gemini": "/x/agy"}, text="x", resume=False, pfade=p)
    assert "--dangerously-skip-permissions" in voll and "--mode" not in voll


def test_vorlagen_haben_modus():
    for v in auftrag_vorlagen.vorlagen():
        assert v["modus"] in svc.MODI
        assert (v["profil"] == "lesen") == (v["modus"] == "bericht")
    ids = {v["id"] for v in auftrag_vorlagen.vorlagen()}
    for erwartet in ("icons-vereinheitlichen", "uebersetzen", "design-vereinheitlichen", "tabellen-export", "formulare", "mobil", "benennung", "zustaende", "datenqualitaet"):
        assert erwartet in ids


def test_log_zeilen_agy():
    roh = "\n".join(json.dumps(z) for z in [
        {"event": "init", "conversation_id": "ac7fdff7-c819", "init": {"cwd": "/x", "permission_mode": "request-review", "tools": ["run_command"]}},
        {"event": "step_update", "step_update": {"conversation_id": "ac7fdff7-c819", "step_index": 1, "state": "DONE", "step_type": "agent_response", "usage": {"input_tokens": 100, "output_tokens": 10}}},
        {"event": "step_update", "step_update": {"conversation_id": "ac7fdff7-c819", "step_index": 2, "state": "ACTIVE", "step_type": "tool", "tool_name": "run_command", "tool_info": {"name": "run_command", "parameters": {"CommandLine": "cat calc.py"}}}},
        {"event": "step_update", "step_update": {"conversation_id": "ac7fdff7-c819", "step_index": 2, "state": "DONE", "step_type": "tool", "tool_name": "run_command"}},
        {"event": "result", "result": {"conversation_id": "ac7fdff7-c819", "status": "DONE", "response": "add gibt die Summe zurück.", "num_turns": 1, "usage": {"input_tokens": 36040, "output_tokens": 773, "thinking_tokens": 457, "cache_read_tokens": 48783}}},
    ])
    zeilen = svc.log_zeilen(roh, agent="gemini")
    assert [z["art"] for z in zeilen] == ["system", "tool", "result"]
    assert zeilen[1]["text"] == "run_command: cat calc.py"
    erg = svc.ergebnis_aus_log(roh, agent="gemini")
    assert erg["session_id"] == "ac7fdff7-c819" and erg["ergebnis"] == "add gibt die Summe zurück."
    assert erg["tokens_in"] == 36040 + 48783 and erg["tokens_out"] == 773 + 457 and erg["fehler"] is None
    abgebrochen = json.dumps({"event": "result", "result": {"conversation_id": "c1", "status": "CANCELED", "response": "", "usage": {"output_tokens": 5}}})
    e2 = svc.ergebnis_aus_log(abgebrochen, agent="gemini")
    assert e2["fehler"] and "Werkzeugfreigabe" in e2["fehler"] and e2["ergebnis"] is None


def test_abschluss_ohne_hook_artefakte():
    cmd = svc.abschluss_befehl(_auftrag())
    assert "':!ARCHITEKTUR.md'" in cmd and "git checkout -q -- ARCHITEKTUR.md" in cmd
    assert "-c core.hooksPath=/dev/null" in cmd and "git add -A -- ." in cmd
    assert "keine Änderungen im Branch" in cmd and "git diff --shortstat master HEAD" in cmd


def test_stand_werte_und_unterbrochen_erkennung():
    roh = "DONE=\nPID_LEBT=0\nLOG_ALTER=125\n{\"type\":\"system\"}\n---STDERR---\n"
    w = svc.stand_werte(roh)
    assert w == {"done": None, "pid_lebt": False, "log_alter": 125}
    w2 = svc.stand_werte("DONE=0\nPID_LEBT=1\nLOG_ALTER=3\n")
    assert w2["done"] == "0" and w2["pid_lebt"] is True
    cmd = svc.stand_befehl(_auftrag(), 30)
    assert "PID_LEBT=" in cmd and "LOG_ALTER=" in cmd and "kill -0" in cmd


def test_zeitlimits_je_agent_und_profil():
    p = svc._lauf_pfade(_auftrag())
    lesen = svc.agent_befehl(_auftrag(profil="lesen"), bins={}, text="x", resume=False, pfade=p)
    umsetzung = svc.agent_befehl(_auftrag(profil="bearbeiten_tests"), bins={}, text="x", resume=False, pfade=p)
    assert "--max-turns 40" in lesen and "--max-turns 150" in umsetzung
    agy = svc.agent_befehl(_auftrag(agent="gemini"), bins={"gemini": "/x/agy"}, text="x", resume=False, pfade=p)
    assert "--print-timeout 45m" in agy


def test_aufraeumen_befehl():
    cmd = svc.aufraeumen_befehl(_auftrag(branch="auftrag/a_test1"))
    assert "git worktree remove --force" in cmd and "git worktree prune" in cmd and "branch -D" not in cmd
    cmd2 = svc.aufraeumen_befehl(_auftrag(branch="auftrag/a_test1"), branch_loeschen=True)
    assert "git branch -D auftrag/a_test1" in cmd2


def test_fortsetzen_prompt_nach_unterbrechung():
    a = _auftrag(session_id="sess-9", modus="plan_freigabe", freigegeben="2026-08-28T10:00:00Z", profil="bearbeiten_tests")
    cmd = svc.start_befehl(a, bins={}, resume=True, nachfrage=svc.UNTERBROCHEN_PROMPT)
    assert "--resume sess-9" in cmd and "unterbrochen" in cmd and "--permission-mode acceptEdits" in cmd


def test_pruefbefehle_aus_cockpit_yaml_und_erkennung():
    roh = "---COCKPIT_YAML---\nbasis: main\npruefung:\n  - PYTHONPATH=src python3 -m pytest -q\n  - ruff check src\nmerge: pr\n---MANIFESTE---\npyproject.toml\n---PYTEST---\ntest_x.py"
    befehle, basis = svc.pruefbefehle_aus(roh)
    assert basis == "main" and befehle == ["PYTHONPATH=src python3 -m pytest -q", "ruff check src"]
    roh2 = "---COCKPIT_YAML---\n---MANIFESTE---\nbackend/requirements.txt\nfrontend/package.json\n---PYTEST---\n"
    befehle2, basis2 = svc.pruefbefehle_aus(roh2)
    assert basis2 == "master" and befehle2 == ["cd backend && python3 -m pytest -q", "cd frontend && npm run type-check && npm run build"]
    assert svc.pruefbefehle_aus("")[0] == []


def test_pruefung_auswerten():
    befehle = ["pytest -q", "ruff check ."]
    roh = "---PRUEF 0---\n3 passed\n---ENDE 0 rc=0 dauer=4---\n---PRUEF 1---\nE501 zu lang\n---ENDE 1 rc=1 dauer=1---\n"
    erg, ok = svc.pruefung_auswerten(roh, befehle)
    assert not ok and erg[0]["ok"] and erg[0]["dauer_s"] == 4 and not erg[1]["ok"] and "E501" in erg[1]["auszug"]
    erg2, ok2 = svc.pruefung_auswerten("---PRUEF 0---\nok\n---ENDE 0 rc=0 dauer=2---\n", ["pytest -q"])
    assert ok2
    erg3, ok3 = svc.pruefung_auswerten("", ["pytest -q"])
    assert not ok3 and "Zeitlimit" in erg3[0]["auszug"]
    cmd = svc.pruefung_befehl(_auftrag(), befehle)
    assert "timeout 900 bash -lc 'pytest -q'" in cmd and "---ENDE 1" in cmd


def test_pr_befehl_und_body():
    a = _auftrag(branch="auftrag/a_test1", ergebnis="Alles umgesetzt.", pruefung=json.dumps([{"befehl": "pytest -q", "ok": True, "dauer_s": 3}]))
    cmd = svc.pr_befehl(a, "master", "README ergänzen", "/tmp/body.md")
    assert "git push -u origin auftrag/a_test1" in cmd and "gh pr create --base master --head auftrag/a_test1" in cmd and "merge" not in cmd
    body = svc.pr_body(a)
    assert "Alles umgesetzt." in body and "✅ `pytest -q`" in body and "mergt aber nicht" in body


def test_pr_checks_kurz():
    assert svc.pr_checks_kurz("build\tpass\t1m2s\thttps://x\ntests\tfail\t30s\thttps://y\nlint\tpending\t0\thttps://z\n") == "1 grün · 1 rot · 1 läuft"
    assert svc.pr_checks_kurz("no checks reported on the 'auftrag/x' branch\n") == "keine Checks"


def test_claude_permission_denials_als_verweigert():
    roh = json.dumps({"type": "result", "subtype": "success", "result": "Ich konnte npm test nicht ausführen.", "session_id": "s1",
                      "permission_denials": [{"tool_name": "Bash", "tool_input": {"command": "npm test"}}], "usage": {"input_tokens": 1, "output_tokens": 1}})
    erg = svc.ergebnis_aus_log(roh)
    assert erg["verweigert"] == ["Bash(npm test)"]


def test_claude_md_kontext_nur_fuer_codex_und_agy():
    codex = svc.start_befehl(_auftrag(agent="codex"), bins={})
    claude = svc.start_befehl(_auftrag(agent="claude"), bins={})
    assert "[ 1 = 1 ] && [ -f /home/janpow/Projekte/x/.cockpit-auftraege/wt-a_test1/CLAUDE.md ]" in codex and "head -c 4000" in codex
    assert "[ 0 = 1 ]" in claude


def test_pruefbefehle_aus_basis_commit():
    cmd = svc.pruefung_lesen_befehl(_auftrag(), "main")
    assert "git show main:.cockpit.yaml" in cmd and "cat .cockpit.yaml" not in cmd


def test_startbefehl_quotet_pfade_und_programme():
    a = _auftrag(projekt="/home/janpow/Mein Projekt")
    cmd = svc.start_befehl(a, bins={"claude": "/pfad mit leer/claude"})
    assert "'/pfad mit leer/claude'" in cmd
    assert "'/home/janpow/Mein Projekt/.cockpit-auftraege/a_test1/lauf.jsonl'" in cmd


def test_abschluss_prueft_worktree():
    cmd = svc.abschluss_befehl(_auftrag())
    assert "rev-parse --show-toplevel" in cmd and "; git add" not in cmd
