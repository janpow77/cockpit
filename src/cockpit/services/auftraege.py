"""Aufträge (Kanban): Claude Code headless je Auftrag in einem eigenen Git-Worktree.

Jede Karte ist ein Auftrag mit Projektverzeichnis auf einem Host. Der Runner (Hintergrund-
lauf) plant nach Priorität und Kontingent, legt auf dem Host einen Worktree samt Branch
``auftrag/<id>`` an und startet dort ``claude -p`` mit ``--output-format stream-json``
(ohne ``--bare``: läuft über die Max-Anmeldung des Nutzers). Fortschritt und Ergebnis
kommen aus der Protokolldatei des Laufs; am Ende wird auf dem Branch committet.

Profile bestimmen die Berechtigungen des Laufs (nie ``--dangerously-skip-permissions``).
"""

from __future__ import annotations

import json
import logging
import re
import shlex
import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import AuftragRow, HostRow
from .ssh_runner import run_on_host

log = logging.getLogger(__name__)

STATUS = ("eingang", "geplant", "laeuft", "rueckfrage", "freigabe", "fertig", "fehler", "abgebrochen")
AGENTEN = ("claude", "codex", "gemini")
# Modus: nur berichten/planen · Plan zeigen und erst nach Freigabe umsetzen · direkt umsetzen
MODI = ("bericht", "plan_freigabe", "umsetzen")
# Antigravity CLI (agy, Google-Abo): Berechtigungen im Druckmodus nur pauschal – Schreibprofile im Sandkasten
PROFILE_AGY: dict[str, str] = {
    "lesen": "--sandbox",
    "bearbeiten": "--sandbox --dangerously-skip-permissions",
    "bearbeiten_tests": "--sandbox --dangerously-skip-permissions",
    "voll": "--sandbox --dangerously-skip-permissions",
}
# Profile je Agent (nie Bypass-Flags):
PROFILE_CODEX: dict[str, str] = {
    "lesen": "-s read-only",
    "bearbeiten": "-s workspace-write --approve-for-me",
    "bearbeiten_tests": "-s workspace-write --approve-for-me",
    "voll": "-s workspace-write --approve-for-me",
}
PROFILE_GEMINI: dict[str, str] = {
    "lesen": "--approval-mode default --skip-trust",
    "bearbeiten": "--approval-mode auto_edit --skip-trust",
    "bearbeiten_tests": "--approval-mode yolo --skip-trust",
    "voll": "--approval-mode yolo --skip-trust",
}
PROFILE: dict[str, str] = {
    # Nur lesen und analysieren
    "lesen": (
        "--permission-mode dontAsk --allowedTools 'Read,Grep,Glob,Bash(git diff *),Bash(git log *),Bash(git status *),"
        "Bash(git show *),Bash(git blame *),Bash(rg *),Bash(gh pr *),Bash(gh issue *),Bash(gh run *),Bash(gh api *),Bash(gh repo view *),"
        "Bash(graphify *),mcp__graphify'"
    ),
    # Dateien aendern
    "bearbeiten": "--permission-mode acceptEdits",
    # Dateien aendern, Tests/Lint laufen lassen, committen
    "bearbeiten_tests": (
        "--permission-mode acceptEdits --allowedTools "
        "'Bash(npm test *),Bash(npm run *),Bash(npx *),Bash(pytest *),Bash(python -m pytest *),Bash(python3 -m pytest *),"
        "Bash(ruff *),Bash(git add *),Bash(git commit *),Bash(git diff *),Bash(git log *),Bash(git status *)'"
    ),
    # Classifier entscheidet
    "voll": "--permission-mode auto",
}
ZEITFENSTER = ("sofort", "nachts", "nach_reset")
MAX_TURNS = 80
LAUF_DIR = ".cockpit-auftraege"  # unterhalb des Projektverzeichnisses (gitignored per Runner)


def _iso(dt: datetime | None = None) -> str:
    return (dt or datetime.now(UTC)).isoformat(timespec="seconds").replace("+00:00", "Z")


def neue_id() -> str:
    return "a_" + uuid.uuid4().hex[:10]


def as_dict(a: AuftragRow) -> dict:
    return {
        "id": a.id, "titel": a.titel, "text": a.text, "host": a.host, "projekt": a.projekt, "agent": a.agent,
        "modus": a.modus, "freigegeben": a.freigegeben,
        "projekt_name": a.projekt_name, "profil": a.profil, "prioritaet": a.prioritaet,
        "zeitfenster": a.zeitfenster, "status": a.status, "reihenfolge": a.reihenfolge,
        "branch": a.branch, "worktree": a.worktree, "session_id": a.session_id,
        "gestartet": a.gestartet, "beendet": a.beendet, "dauer_s": a.dauer_s,
        "ergebnis": a.ergebnis, "fehler": a.fehler, "kosten_usd": a.kosten_usd,
        "tokens_in": a.tokens_in, "tokens_out": a.tokens_out, "turns": a.turns,
        "letzte_zeile": a.letzte_zeile, "diff_url": a.diff_url, "erstellt": a.erstellt, "aktualisiert": a.aktualisiert,
    }


# ---------------------------------------------------------------------------
# Persistenz
# ---------------------------------------------------------------------------


def liste(session: Session) -> list[AuftragRow]:
    return list(session.execute(select(AuftragRow).order_by(AuftragRow.reihenfolge.asc(), AuftragRow.erstellt.asc())).scalars())


def holen(session: Session, auftrag_id: str) -> AuftragRow | None:
    return session.get(AuftragRow, auftrag_id)


def anlegen(session: Session, **felder) -> AuftragRow:
    jetzt = _iso()
    reihenfolge = (max((a.reihenfolge for a in liste(session)), default=0) or 0) + 10
    a = AuftragRow(id=neue_id(), status=felder.pop("status", "eingang"), reihenfolge=reihenfolge, erstellt=jetzt, aktualisiert=jetzt, **felder)
    session.add(a)
    session.commit()
    session.refresh(a)
    return a


def aendern(session: Session, a: AuftragRow, **felder) -> AuftragRow:
    for k, v in felder.items():
        setattr(a, k, v)
    a.aktualisiert = _iso()
    session.commit()
    session.refresh(a)
    return a


# ---------------------------------------------------------------------------
# Kontingent (rein, testbar)
# ---------------------------------------------------------------------------


def parallel_max(fuenf_stunden_pct: float | None, woche_pct: float | None, basis: int = 3) -> tuple[int, str | None]:
    """Wie viele Laeufe gleichzeitig: haengt an der Auslastung des 5-Stunden-Fensters."""
    if woche_pct is not None and woche_pct >= 98:
        return 0, f"Wochenlimit ausgeschöpft ({int(woche_pct)} %)"
    if fuenf_stunden_pct is None:
        return max(1, basis - 1), "Auslastung unbekannt – gedrosselt"
    if fuenf_stunden_pct >= 95:
        return 0, f"5-Stunden-Fenster ausgeschöpft ({int(fuenf_stunden_pct)} %)"
    if fuenf_stunden_pct >= 85:
        return 1, f"5-Stunden-Fenster bei {int(fuenf_stunden_pct)} % – nur ein Lauf"
    if fuenf_stunden_pct >= 60:
        return max(1, basis - 1), None
    return basis, None


def zeitfenster_offen(zeitfenster: str, jetzt: datetime, reset_woche: datetime | None = None) -> bool:
    if zeitfenster == "nachts":
        return jetzt.hour >= 22 or jetzt.hour < 7
    if zeitfenster == "nach_reset":
        return reset_woche is not None and jetzt >= reset_woche
    return True


# ---------------------------------------------------------------------------
# Lauf auf dem Host
# ---------------------------------------------------------------------------


def _lauf_pfade(a: AuftragRow) -> dict[str, str]:
    basis = f"{a.projekt.rstrip('/')}/{LAUF_DIR}/{a.id}"
    return {
        "basis": basis,
        "worktree": f"{a.projekt.rstrip('/')}/{LAUF_DIR}/wt-{a.id}",
        "log": f"{basis}/lauf.jsonl",
        "stderr": f"{basis}/stderr.txt",
        "done": f"{basis}/done.txt",
        "pid": f"{basis}/pid.txt",
        "prompt": f"{basis}/auftrag.txt",
    }


def phase(a: AuftragRow) -> str:
    """'plan' = nur lesen und berichten/planen; 'umsetzung' = Dateien ändern erlaubt (rein, testbar)."""
    modus = getattr(a, "modus", "umsetzen") or "umsetzen"
    if modus == "umsetzen":
        return "umsetzung"
    if modus == "plan_freigabe" and getattr(a, "freigegeben", None):
        return "umsetzung"
    return "plan"


def effektives_profil(a: AuftragRow) -> str:
    """Berichts-/Planphase läuft immer im Leseprofil; die Umsetzung mit dem Profil der Karte."""
    return "lesen" if phase(a) == "plan" else a.profil


PLAN_SUFFIX = {
    "bericht": (
        "\n\n[Modus: nur Bericht] Ändere KEINE Dateien und führe keine schreibenden Befehle aus. "
        "Analysiere, berichte und schlage einen konkreten Umsetzungsplan vor: nummerierte Schritte, betroffene Dateien (Datei:Zeile), Risiken, nötige Tests, geschätzter Umfang."
    ),
    "plan_freigabe": (
        "\n\n[Modus: Plan mit Freigabe] Ändere jetzt noch KEINE Dateien. Erstelle zuerst einen Umsetzungsplan: nummerierte Schritte, betroffene Dateien (Datei:Zeile), "
        "Risiken, nötige Tests, geschätzter Umfang. Ich prüfe den Plan und gebe ihn frei – erst danach wird in derselben Sitzung umgesetzt."
    ),
}
UMSETZUNG_TEXT = (
    "Freigegeben. Setze den Plan jetzt vollständig um – in derselben Reihenfolge, mit Tests/Lint/Build nach Konvention des Repos und kleinen, sprechenden Commits. "
    "{hinweis}Berichte am Ende: was geändert wurde, was offen blieb, welche Tests liefen."
)


def prompt_fuer(a: AuftragRow, *, resume: bool = False, nachfrage: str | None = None) -> str:
    """Auftragstext für den Lauf: Nachfrage bei Fortsetzung, sonst Text plus Modus-Zusatz in der Planphase (rein, testbar)."""
    if resume and nachfrage:
        return nachfrage
    text = a.text
    if phase(a) == "plan":
        text += PLAN_SUFFIX.get(getattr(a, "modus", "") or "", PLAN_SUFFIX["bericht"])
    return text


def umsetzungstext(hinweis: str | None = None) -> str:
    h = (hinweis or "").strip()
    return UMSETZUNG_TEXT.format(hinweis=(f"Hinweis: {h} " if h else ""))


def status_nach_erfolg(a: AuftragRow, ergebnis: str | None) -> str:
    """Nach erfolgreichem Lauf: Plan wartet auf Freigabe, Frage → Rückfrage, sonst fertig (rein, testbar)."""
    if (getattr(a, "modus", "") or "") == "plan_freigabe" and not getattr(a, "freigegeben", None):
        return "freigabe"
    return "rueckfrage" if ist_rueckfrage(ergebnis) else "fertig"


def agent_befehl(a: AuftragRow, *, bins: dict[str, str], text: str, resume: bool, pfade: dict[str, str]) -> str:
    """Der eigentliche Agentenaufruf im Worktree (rein, testbar). Ausgabe als JSON-Zeilen ins Protokoll."""
    prompt = f'"$(cat {pfade["prompt"]})"'
    profil = effektives_profil(a)
    if a.agent == "codex":
        bin_ = bins.get("codex", "codex")
        flags = PROFILE_CODEX.get(profil, PROFILE_CODEX["bearbeiten"])
        if resume and a.session_id:
            # `exec resume` kennt weder -s noch --approve-for-me: Sandbox/Freigabe als Konfigurations-Overrides
            sandbox = "read-only" if profil == "lesen" else "workspace-write"
            return (
                f"{bin_} exec resume {shlex.quote(a.session_id)} {prompt} --json --skip-git-repo-check "
                f"-c sandbox_mode={shlex.quote(sandbox)} -c approval_policy=never"
            )
        return f"{bin_} exec {prompt} --json {flags} --skip-git-repo-check"
    if a.agent == "gemini":
        bin_ = bins.get("gemini", "gemini")
        if bin_.rstrip("/").rsplit("/", 1)[-1] == "agy":
            # Antigravity CLI (Google-Abo): agy -p … --output-format stream-json, Fortsetzung über --conversation <id>
            flags = PROFILE_AGY.get(profil, PROFILE_AGY["bearbeiten"])
            resume_flag = f"--conversation {shlex.quote(a.session_id)}" if resume and a.session_id else ""
            return f"{bin_} -p {prompt} --output-format stream-json {flags} {resume_flag}".strip()
        flags = PROFILE_GEMINI.get(profil, PROFILE_GEMINI["bearbeiten"])
        resume_flag = f"--resume {shlex.quote(a.session_id)}" if resume and a.session_id else ""
        return f"{bin_} -p {prompt} -o stream-json {flags} {resume_flag}".strip()
    bin_ = bins.get("claude", "claude")
    flags = PROFILE.get(profil, PROFILE["bearbeiten"])
    resume_flag = f"--resume {shlex.quote(a.session_id)}" if resume and a.session_id else ""
    return f"{bin_} -p {prompt} {flags} {resume_flag} --output-format stream-json --verbose --max-turns {MAX_TURNS}".replace("  ", " ")


def start_befehl(a: AuftragRow, *, bins: dict[str, str] | None = None, resume: bool = False, nachfrage: str | None = None) -> str:
    """Shell-Befehl fuer den Start auf dem Host (rein, testbar): Worktree anlegen, Agent im Hintergrund."""
    p = _lauf_pfade(a)
    branch = a.branch or f"auftrag/{a.id}"
    text = prompt_fuer(a, resume=resume, nachfrage=nachfrage)
    lauf = agent_befehl(a, bins=bins or {}, text=text, resume=resume, pfade=p)
    wt = shlex.quote(p["worktree"])
    lauf_hinten = f"{lauf} > {p['log']} 2> {p['stderr']}; echo $? > {p['done']}"
    teile = [
        f"mkdir -p {shlex.quote(p['basis'])}",
        f"cd {shlex.quote(a.projekt)}",
        # Laufverzeichnis nie mit einchecken (neues git legt .git/info nicht an; Fehler hier sind unkritisch)
        f"{{ mkdir -p .git/info && {{ grep -qx '{LAUF_DIR}/' .git/info/exclude 2>/dev/null || echo '{LAUF_DIR}/' >> .git/info/exclude; }}; }} 2>/dev/null || true",
        f"{{ [ -d {wt} ] || git worktree add -B {shlex.quote(branch)} {wt} >/dev/null 2>&1 || git worktree add {wt} {shlex.quote(branch)} >/dev/null 2>&1; }}",
        f"printf '%s' {shlex.quote(text)} > {shlex.quote(p['prompt'])}",
        f"rm -f {shlex.quote(p['done'])}",
        f"cd {wt}",
        # Start in einer Untershell, sonst löst das & die ganze &&-Kette in den Hintergrund; $! ist die PID der Hülle (Elternprozess des Agenten)
        f"( nohup bash -c {shlex.quote(lauf_hinten)} >/dev/null 2>&1 & echo $! > {shlex.quote(p['pid'])} )",
        "echo gestartet",
    ]
    return " && ".join(teile)


def stopp_befehl(a: AuftragRow) -> str:
    p = _lauf_pfade(a)
    return f"pid=$(cat {shlex.quote(p['pid'])} 2>/dev/null); [ -n \"$pid\" ] && pkill -INT -P \"$pid\" 2>/dev/null; sleep 2; [ -n \"$pid\" ] && pkill -TERM -P \"$pid\" 2>/dev/null; echo gestoppt"


def stand_befehl(a: AuftragRow, zeilen: int = 60) -> str:
    """Liefert done-Code (oder leer), dann die letzten Protokollzeilen."""
    p = _lauf_pfade(a)
    return f"echo \"DONE=$(cat {shlex.quote(p['done'])} 2>/dev/null)\"; tail -n {int(zeilen)} {shlex.quote(p['log'])} 2>/dev/null; echo '---STDERR---'; tail -n 5 {shlex.quote(p['stderr'])} 2>/dev/null"


def abschluss_befehl(a: AuftragRow) -> str:
    """Aenderungen im Worktree committen und Kennzahlen des Diffs liefern."""
    p = _lauf_pfade(a)
    msg = f"auftrag {a.id}: {a.titel}"[:120]
    return (
        f"cd {shlex.quote(p['worktree'])} && git add -A && "
        f"(git diff --cached --quiet || git -c user.name=cockpit -c user.email=cockpit@flowaudit.de commit -q -m {shlex.quote(msg)}) ; "
        "echo \"COMMITS=$(git rev-list --count HEAD ^$(git merge-base HEAD $(git rev-parse --abbrev-ref HEAD@{upstream} 2>/dev/null || echo master) 2>/dev/null || echo HEAD) 2>/dev/null)\"; "
        "echo \"HEAD=$(git rev-parse --short HEAD)\"; git diff --shortstat HEAD~1 HEAD 2>/dev/null | head -1"
    )


# ---------------------------------------------------------------------------
# Protokoll (stream-json) auswerten (rein, testbar)
# ---------------------------------------------------------------------------


def _codex_zeile(d: dict) -> dict | None:
    """Codex `exec --json`: thread.started, item.completed (agent_message, command_execution, …), turn.completed."""
    typ = d.get("type") or ""
    if typ == "thread.started":
        return {"ts": None, "art": "system", "text": f"Codex-Sitzung {str(d.get('thread_id', ''))[:8]}"}
    if typ in ("item.completed", "item.started"):
        item = d.get("item") or {}
        it = item.get("type") or ""
        if it == "agent_message" and item.get("text"):
            return {"ts": None, "art": "text", "text": str(item["text"]).strip()[:1500]}
        if it in ("command_execution", "file_change", "mcp_tool_call", "web_search") and typ == "item.started":
            kurz = item.get("command") or ", ".join(str(c.get("path", "")) for c in (item.get("changes") or [])[:3]) or item.get("server") or item.get("query") or ""
            return {"ts": None, "art": "tool", "text": f"{it}: {str(kurz)[:200]}"}
        if it == "reasoning":
            return None
    if typ == "turn.completed":
        u = d.get("usage") or {}
        return {"ts": None, "art": "result", "text": f"Ende · {u.get('output_tokens', 0)} Ausgabe-Tokens"}
    if typ == "turn.failed" or typ == "error":
        return {"ts": None, "art": "fehler", "text": str((d.get("error") or {}).get("message") or d.get("message") or "Fehler")[:300]}
    return None


def _gemini_zeile(d: dict) -> dict | None:
    """Gemini CLI stream-json (Format variiert je Version): Text, Werkzeuge, Ergebnis generisch."""
    typ = str(d.get("type") or d.get("event") or "")
    if typ in ("init", "session"):
        return {"ts": None, "art": "system", "text": f"Gemini-Sitzung {str(d.get('session_id', ''))[:8]}"}
    if typ in ("tool_use", "tool_call", "tool"):
        return {"ts": None, "art": "tool", "text": f"{d.get('name') or d.get('tool_name') or 'Werkzeug'}: {str(d.get('input') or d.get('args') or '')[:200]}"}
    if typ in ("result", "done", "complete"):
        return {"ts": None, "art": "result", "text": str(d.get("result") or d.get("response") or d.get("status") or "Ende")[:3000]}
    if typ in ("message", "assistant", "content") or (d.get("role") == "assistant"):
        text = d.get("content") or d.get("text") or d.get("delta") or ""
        if isinstance(text, list):
            text = " ".join(str(t.get("text", "")) for t in text if isinstance(t, dict))
        if str(text).strip():
            return {"ts": None, "art": "text", "text": str(text).strip()[:1500]}
    if typ in ("error",):
        return {"ts": None, "art": "fehler", "text": str(d.get("message") or d.get("error") or "Fehler")[:300]}
    return None


def log_zeilen(roh: str, max_zeilen: int = 80, agent: str = "claude") -> list[dict]:
    """Protokoll → lesbare Zeilen: Text des Assistenten, Werkzeugaufrufe, Ergebnis."""
    out: list[dict] = []
    for line in roh.splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            d = json.loads(line)
        except ValueError:
            continue
        if agent == "codex":
            z = _codex_zeile(d)
            if z:
                out.append(z)
            continue
        if agent == "gemini":
            z = _gemini_zeile(d)
            if z:
                out.append(z)
            continue
        typ = d.get("type")
        ts = d.get("timestamp")
        if typ == "assistant":
            for block in (d.get("message") or {}).get("content") or []:
                if block.get("type") == "text" and block.get("text", "").strip():
                    out.append({"ts": ts, "art": "text", "text": block["text"].strip()[:1500]})
                elif block.get("type") == "tool_use":
                    inp = block.get("input") or {}
                    kurz = inp.get("command") or inp.get("file_path") or inp.get("pattern") or inp.get("description") or ""
                    out.append({"ts": ts, "art": "tool", "text": f"{block.get('name')}: {str(kurz)[:200]}"})
        elif typ == "result":
            txt = d.get("result") or ""
            kosten = d.get("total_cost_usd")
            out.append({"ts": ts, "art": "result", "text": (str(txt).strip()[:3000] or d.get("subtype") or "Ende") + (f"  ·  {kosten:.2f} $" if isinstance(kosten, (int, float)) else "")})
        elif typ == "system" and d.get("subtype") in ("init", "api_retry"):
            if d.get("subtype") == "api_retry":
                out.append({"ts": ts, "art": "system", "text": f"API-Wiederholung {d.get('attempt')}/{d.get('max_retries')} ({d.get('error')})"})
            else:
                out.append({"ts": ts, "art": "system", "text": f"Sitzung {d.get('session_id', '')[:8]} · Modell {d.get('model', '?')}"})
    return out[-max_zeilen:]


def _ergebnis_codex(roh: str) -> dict | None:
    thread = None
    text = None
    usage: dict = {}
    fehler = None
    for line in roh.splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            d = json.loads(line)
        except ValueError:
            continue
        if d.get("type") == "thread.started":
            thread = d.get("thread_id")
        elif d.get("type") == "item.completed" and (d.get("item") or {}).get("type") == "agent_message":
            text = (d["item"].get("text") or text)
        elif d.get("type") == "turn.completed":
            usage = d.get("usage") or usage
        elif d.get("type") in ("turn.failed", "error"):
            fehler = str((d.get("error") or {}).get("message") or d.get("message") or "Fehler")[:500]
    if thread is None and text is None and not fehler:
        return None
    return {
        "ergebnis": (text or "").strip() or None, "fehler": fehler, "subtype": None, "kosten_usd": None,
        "tokens_in": (usage.get("input_tokens") or 0) + (usage.get("cached_input_tokens") or 0) or None,
        "tokens_out": usage.get("output_tokens"), "turns": None, "session_id": thread, "dauer_ms": None,
    }


def _ergebnis_gemini(roh: str) -> dict | None:
    sid = None
    text = None
    fehler = None
    stats: dict = {}
    for line in roh.splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            d = json.loads(line)
        except ValueError:
            continue
        typ = str(d.get("type") or d.get("event") or "")
        if d.get("conversation_id") or (typ in ("init", "session") and d.get("session_id")):
            sid = d.get("conversation_id") or d.get("session_id")
        z = _gemini_zeile(d)
        if z and z["art"] == "text":
            text = z["text"]
        if z and z["art"] == "result" and d.get("result"):
            text = str(d.get("result"))
        if z and z["art"] == "fehler":
            fehler = z["text"]
        if isinstance(d.get("stats"), dict):
            stats = d["stats"]
    if sid is None and text is None and not fehler:
        return None
    tok = stats.get("total_tokens") or stats.get("tokens") or {}
    return {"ergebnis": text, "fehler": fehler, "subtype": None, "kosten_usd": None,
            "tokens_in": (tok.get("input") if isinstance(tok, dict) else None), "tokens_out": (tok.get("output") if isinstance(tok, dict) else None),
            "turns": None, "session_id": sid, "dauer_ms": None}


def ergebnis_aus_log(roh: str, agent: str = "claude") -> dict | None:
    """Letztes Ergebnis: Text, Kosten, Tokens, Sitzung, Fehlerkennzeichen (je Agent)."""
    if agent == "codex":
        return _ergebnis_codex(roh)
    if agent == "gemini":
        return _ergebnis_gemini(roh)
    letztes = None
    session_id = None
    for line in roh.splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            d = json.loads(line)
        except ValueError:
            continue
        if d.get("type") == "system" and d.get("subtype") == "init":
            session_id = d.get("session_id")
        if d.get("type") == "result":
            letztes = d
    if letztes is None:
        return None
    usage = letztes.get("usage") or {}
    return {
        "ergebnis": str(letztes.get("result") or "").strip() or None,
        "fehler": None if not letztes.get("is_error") else str(letztes.get("result") or letztes.get("subtype") or "Fehler")[:500],
        "subtype": letztes.get("subtype"),
        "kosten_usd": letztes.get("total_cost_usd"),
        "tokens_in": (usage.get("input_tokens") or 0) + (usage.get("cache_read_input_tokens") or 0) + (usage.get("cache_creation_input_tokens") or 0) or None,
        "tokens_out": usage.get("output_tokens"),
        "turns": letztes.get("num_turns"),
        "session_id": letztes.get("session_id") or session_id,
        "dauer_ms": letztes.get("duration_ms"),
    }


def ist_rueckfrage(ergebnis: str | None) -> bool:
    """Endet die Antwort mit einer Frage an den Nutzer? (rein, testbar)"""
    if not ergebnis:
        return False
    schluss = ergebnis.strip()[-400:]
    return bool(re.search(r"\?\s*$", schluss)) or bool(re.search(r"(soll ich|möchtest du|willst du|welche .* bevorzugst)", schluss, re.I))


VORSCHLAG_PRAEFIX = "Vorschlag: "


def vorschlaege_aus_ergebnis(ergebnis: str | None) -> list[dict]:
    """Letzter JSON-Block eines Vorschlags-Laufs → Liste {titel, text, profil, prioritaet, begruendung} (rein, testbar)."""
    if not ergebnis:
        return []
    bloecke = re.findall(r"```(?:json)?\s*(\[.*?\])\s*```", ergebnis, re.S)
    roh = bloecke[-1] if bloecke else None
    if roh is None:
        m = re.search(r"\[\s*\{.*\}\s*\]\s*$", ergebnis.strip(), re.S)
        roh = m.group(0) if m else None
    if not roh:
        return []
    try:
        daten = json.loads(roh)
    except ValueError:
        return []
    out: list[dict] = []
    for d in daten if isinstance(daten, list) else []:
        if not isinstance(d, dict) or not d.get("titel") or not d.get("text"):
            continue
        profil = str(d.get("profil") or "bearbeiten")
        if profil not in PROFILE:
            profil = "bearbeiten"
        try:
            prio = max(1, min(5, int(d.get("prioritaet") or 3)))
        except (TypeError, ValueError):
            prio = 3
        out.append({
            "titel": str(d["titel"]).strip()[:150], "text": str(d["text"]).strip()[:12000],
            "profil": profil, "prioritaet": prio, "begruendung": str(d.get("begruendung") or "").strip()[:300],
        })
    return out[:12]


def vorschlaege_eintragen(session: Session, quelle: AuftragRow) -> int:
    """Vorschläge eines beendeten Vorschlags-Laufs als Karten in den Eingang legen (Dubletten nach Titel je Projekt vermeiden)."""
    vorschlaege = vorschlaege_aus_ergebnis(quelle.ergebnis)
    if not vorschlaege:
        return 0
    vorhanden = {(a.projekt, a.titel.lower()) for a in liste(session)}
    n = 0
    for v in vorschlaege:
        titel = (VORSCHLAG_PRAEFIX + v["titel"])[:160]
        if (quelle.projekt, titel.lower()) in vorhanden:
            continue
        text = v["text"] + (f"\n\nBegründung: {v['begruendung']}" if v.get("begruendung") else "") + f"\n\n(aus Vorschlags-Lauf {quelle.id} vom {quelle.beendet or quelle.aktualisiert})"
        anlegen(session, titel=titel, text=text, host=quelle.host, projekt=quelle.projekt, projekt_name=quelle.projekt_name,
                agent=quelle.agent, profil=v["profil"], prioritaet=v["prioritaet"], zeitfenster="sofort", status="eingang")
        vorhanden.add((quelle.projekt, titel.lower()))
        n += 1
    return n


def ist_vorschlagslauf(a: AuftragRow) -> bool:
    return a.titel.startswith("Vorschläge einholen") or "\"begruendung\"" in (a.text or "")


def diff_url(github_html_url: str | None, basis_branch: str, branch: str) -> str | None:
    if not github_html_url or not branch:
        return None
    return f"{github_html_url.rstrip('/')}/compare/{basis_branch}...{branch.replace('/', '%2F')}"


# ---------------------------------------------------------------------------
# Host-Aufrufe
# ---------------------------------------------------------------------------


def host_fuer(session: Session, name: str) -> HostRow | None:
    from ..crud import hosts as crud_hosts
    from .host_stats import _ziel

    h = next((x for x in crud_hosts.list_hosts(session) if x.name == name and x.enabled), None)
    return _ziel(h) if h else None


def starten(session: Session, a: AuftragRow, *, bins: dict[str, str], resume: bool = False, nachfrage: str | None = None) -> AuftragRow:
    host = host_fuer(session, a.host)
    if host is None:
        return aendern(session, a, status="fehler", fehler=f"Host {a.host} nicht verfügbar", beendet=_iso())
    branch = a.branch or f"auftrag/{a.id}"
    p = _lauf_pfade(a)
    try:
        res = run_on_host(host, f"bash -lc {shlex.quote(start_befehl(a, bins=bins, resume=resume, nachfrage=nachfrage))}", timeout=60)
    except Exception as exc:  # noqa: BLE001
        return aendern(session, a, status="fehler", fehler=str(exc)[:300], beendet=_iso())
    if not res.ok or "gestartet" not in res.stdout:
        return aendern(session, a, status="fehler", fehler=(res.stderr or res.stdout or "Start fehlgeschlagen")[:300], beendet=_iso())
    return aendern(
        session, a, status="laeuft", branch=branch, worktree=p["worktree"], gestartet=_iso(), beendet=None,
        fehler=None, letzte_zeile="gestartet …", ergebnis=None if not resume else a.ergebnis,
    )


def stoppen(session: Session, a: AuftragRow) -> AuftragRow:
    host = host_fuer(session, a.host)
    if host is not None:
        try:
            run_on_host(host, stopp_befehl(a), timeout=20)
        except Exception as exc:  # noqa: BLE001
            log.warning("Auftrag %s stoppen: %s", a.id, exc)
    return aendern(session, a, status="abgebrochen", beendet=_iso(), letzte_zeile="abgebrochen")


def stand_pruefen(session: Session, a: AuftragRow, github_url: str | None = None) -> AuftragRow:
    """Protokoll des laufenden Auftrags lesen; bei Ende Ergebnis uebernehmen und committen."""
    host = host_fuer(session, a.host)
    if host is None:
        return a
    try:
        res = run_on_host(host, stand_befehl(a, 120), timeout=25)
    except Exception as exc:  # noqa: BLE001
        log.warning("Auftrag %s Stand: %s", a.id, exc)
        return a
    roh = res.stdout or ""
    done = None
    m = re.match(r"DONE=(\S*)", roh)
    if m:
        done = m.group(1) or None
    stderr_teil = roh.split("---STDERR---", 1)[1].strip() if "---STDERR---" in roh else ""
    zeilen = log_zeilen(roh, max_zeilen=3, agent=a.agent)
    letzte = zeilen[-1]["text"] if zeilen else a.letzte_zeile
    gestartet = datetime.fromisoformat(a.gestartet.replace("Z", "+00:00")) if a.gestartet else datetime.now(UTC)
    dauer = int((datetime.now(UTC) - gestartet).total_seconds())
    if done is None:
        return aendern(session, a, letzte_zeile=(letzte or "")[:200], dauer_s=dauer)
    # Lauf beendet
    erg = ergebnis_aus_log(roh, agent=a.agent) or {}
    felder: dict = {
        "beendet": _iso(), "dauer_s": dauer, "session_id": erg.get("session_id") or a.session_id,
        "ergebnis": erg.get("ergebnis") or a.ergebnis, "kosten_usd": erg.get("kosten_usd"),
        "tokens_in": erg.get("tokens_in"), "tokens_out": erg.get("tokens_out"), "turns": erg.get("turns"),
    }
    if done != "0" or erg.get("fehler"):
        felder["status"] = "fehler"
        felder["fehler"] = (erg.get("fehler") or stderr_teil or f"claude beendet mit Code {done}")[:500]
        felder["letzte_zeile"] = "fehlgeschlagen"
        return aendern(session, a, **felder)
    # Aenderungen committen (Profil lesen: nichts zu committen)
    try:
        ab = run_on_host(host, abschluss_befehl(a), timeout=40)
        kopf = re.search(r"HEAD=(\w+)", ab.stdout or "")
        felder["letzte_zeile"] = (ab.stdout or "").strip().splitlines()[-1][:200] if (ab.stdout or "").strip() else "fertig"
        if kopf and github_url:
            felder["diff_url"] = diff_url(github_url, "master", a.branch or f"auftrag/{a.id}")
    except Exception as exc:  # noqa: BLE001
        log.warning("Auftrag %s Abschluss: %s", a.id, exc)
    felder["status"] = status_nach_erfolg(a, felder.get("ergebnis"))
    if felder["status"] == "freigabe":
        felder["letzte_zeile"] = "Plan liegt vor – Freigabe im Kanban"
    return aendern(session, a, **felder)


def umsetzen(session: Session, a: AuftragRow, *, bins: dict[str, str], hinweis: str | None = None) -> AuftragRow:
    """Freigabe eines Plans: Sitzung fortsetzen, jetzt mit Schreibprofil."""
    a = aendern(session, a, freigegeben=_iso(), text=f"{a.text}\n\n--- Freigabe ---\n{umsetzungstext(hinweis)}")
    return starten(session, a, bins=bins, resume=True, nachfrage=umsetzungstext(hinweis))
