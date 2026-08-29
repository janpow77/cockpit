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

STATUS = ("eingang", "geplant", "laeuft", "rueckfrage", "freigabe", "unterbrochen", "fertig", "fehler", "abgebrochen")
AGENTEN = ("claude", "codex", "gemini")
AGENT_AUTO = "auto"
# Modus: nur berichten/planen · Plan zeigen und erst nach Freigabe umsetzen · direkt umsetzen
MODI = ("bericht", "plan_freigabe", "umsetzen")
# Antigravity CLI (agy 1.1.22, Google-Abo): --mode plan (nur lesen/planen) bzw. accept-edits (Dateiänderungen ohne Nachfrage).
# Im Druckmodus kann agy keine Freigabe erfragen: jedes Kommando außerhalb der Allow-Regeln (~/.gemini/antigravity-cli/settings.json)
# bricht den ganzen Lauf mit CANCELED ab – daher Werkzeugfreigabe automatisch (wie Codex ohne Sandbox auf dem NUC);
# Schutz bleibt Worktree + Branch, der Ausführungsmodus begrenzt Dateiänderungen. --sandbox scheitert auf dem NUC.
PROFILE_AGY: dict[str, str] = {
    "lesen": "--mode plan --dangerously-skip-permissions",
    "bearbeiten": "--mode accept-edits --dangerously-skip-permissions",
    "bearbeiten_tests": "--mode accept-edits --dangerously-skip-permissions",
    "voll": "--dangerously-skip-permissions",
}
# Profile je Agent (nie Bypass-Flags):
PROFILE_CODEX: dict[str, str] = {
    "lesen": "-s read-only",
    "bearbeiten": "-s workspace-write --approve-for-me",
    "bearbeiten_tests": "-s workspace-write --approve-for-me",
    "voll": "-s workspace-write --approve-for-me",
}
# Codex-Sandbox (bubblewrap) ist auf dem NUC nicht nutzbar (RTM_NEWADDR: Operation not permitted) – dann läuft Codex
# ohne Isolierung; Schutz durch eigenen Worktree und Branch. Einstellung codex_sandbox: "danger-full-access" | "workspace-write"
CODEX_SANDBOX_VORGABE = "danger-full-access"


def codex_flags(profil: str, sandbox: str | None, resume: bool) -> str:
    """Sandbox-/Freigabe-Flags für Codex (rein, testbar). `exec resume` kennt nur -c-Overrides."""
    if (sandbox or CODEX_SANDBOX_VORGABE) == "danger-full-access":
        return "-c sandbox_mode=danger-full-access -c approval_policy=never" if resume else "-s danger-full-access -c approval_policy=never"
    if resume:
        return f"-c sandbox_mode={'read-only' if profil == 'lesen' else 'workspace-write'} -c approval_policy=never"
    return PROFILE_CODEX.get(profil, PROFILE_CODEX["bearbeiten"])
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
        "Bash(git show *),Bash(git blame *),Bash(rg *),Bash(gh pr list *),Bash(gh pr view *),Bash(gh pr diff *),Bash(gh pr checks *),"
        "Bash(gh issue list *),Bash(gh issue view *),Bash(gh run list *),Bash(gh run view *),Bash(gh repo view *),"
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
MAX_TURNS = 80  # Rückfalloption
# Zughöchstzahl je Profil (Claude): Berichte kurz, Umsetzungen brauchen Luft
MAX_TURNS_PROFIL: dict[str, int] = {"lesen": 40, "bearbeiten": 120, "bearbeiten_tests": 150, "voll": 150}
AGY_PRINT_TIMEOUT = "45m"  # Vorgabe von agy wären 5 min – zu kurz für Umsetzungen
LAUF_DIR = ".cockpit-auftraege"  # unterhalb des Projektverzeichnisses (gitignored per Runner)


def _iso(dt: datetime | None = None) -> str:
    return (dt or datetime.now(UTC)).isoformat(timespec="seconds").replace("+00:00", "Z")


def neue_id() -> str:
    return "a_" + uuid.uuid4().hex[:10]


def as_dict(a: AuftragRow) -> dict:
    return {
        "id": a.id, "titel": a.titel, "text": a.text, "host": a.host, "projekt": a.projekt, "agent": a.agent,
        "modus": a.modus, "freigegeben": a.freigegeben, "agent_auto": bool(a.agent_auto), "agent_grund": a.agent_grund,
        "projekt_name": a.projekt_name, "profil": a.profil, "prioritaet": a.prioritaet,
        "zeitfenster": a.zeitfenster, "status": a.status, "reihenfolge": a.reihenfolge,
        "branch": a.branch, "worktree": a.worktree, "session_id": a.session_id,
        "gestartet": a.gestartet, "beendet": a.beendet, "dauer_s": a.dauer_s,
        "ergebnis": a.ergebnis, "fehler": a.fehler, "kosten_usd": a.kosten_usd,
        "tokens_in": a.tokens_in, "tokens_out": a.tokens_out, "turns": a.turns,
        "letzte_zeile": a.letzte_zeile, "diff_url": a.diff_url, "erstellt": a.erstellt, "aktualisiert": a.aktualisiert,
        "pruefung": json.loads(a.pruefung) if a.pruefung else None, "pruefung_ok": (None if a.pruefung_ok is None else bool(a.pruefung_ok)),
        "pr_url": a.pr_url, "pr_checks": a.pr_checks,
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
    prompt = f'"$(cat {shlex.quote(pfade["prompt"])})"'
    profil = effektives_profil(a)
    if a.agent == "codex":
        bin_ = shlex.quote(bins.get("codex", "codex"))
        sandbox = bins.get("codex_sandbox")
        if resume and a.session_id:
            # Nach hartem Abbruch hält Codex eine Schreibsperre auf den Thread (~/.codex/thread-writer-locks) –
            # der Prozess ist nachweislich tot (unterbrochen), die Sperre darf weg, sonst „already has an active writer“
            sperre = f"rm -f \"$HOME\"/.codex/thread-writer-locks/*{shlex.quote(a.session_id)}* 2>/dev/null; "
            return f"{sperre}{bin_} exec resume {shlex.quote(a.session_id)} {prompt} --json --skip-git-repo-check {codex_flags(profil, sandbox, True)}"
        return f"{bin_} exec {prompt} --json {codex_flags(profil, sandbox, False)} --skip-git-repo-check"
    if a.agent == "gemini":
        bin_ = shlex.quote(bins.get("gemini", "gemini"))
        if bin_.rstrip("/").rsplit("/", 1)[-1] == "agy":
            # Antigravity CLI (Google-Abo): agy -p … --output-format stream-json, Fortsetzung über --conversation <id>
            flags = PROFILE_AGY.get(profil, PROFILE_AGY["bearbeiten"])
            resume_flag = f"--conversation {shlex.quote(a.session_id)}" if resume and a.session_id else ""
            # ohne --add-dir schreibt agy in sein eigenes Scratch-Verzeichnis statt in den Worktree
            return f"{bin_} -p {prompt} --output-format stream-json --print-timeout {AGY_PRINT_TIMEOUT} {flags} --add-dir {shlex.quote(pfade['worktree'])} {resume_flag}".strip()
        flags = PROFILE_GEMINI.get(profil, PROFILE_GEMINI["bearbeiten"])
        resume_flag = f"--resume {shlex.quote(a.session_id)}" if resume and a.session_id else ""
        return f"{bin_} -p {prompt} -o stream-json {flags} {resume_flag}".strip()
    bin_ = shlex.quote(bins.get("claude", "claude"))
    flags = PROFILE.get(profil, PROFILE["bearbeiten"])
    resume_flag = f"--resume {shlex.quote(a.session_id)}" if resume and a.session_id else ""
    max_turns = MAX_TURNS_PROFIL.get(profil, MAX_TURNS)
    return f"{bin_} -p {prompt} {flags} {resume_flag} --output-format stream-json --verbose --max-turns {max_turns}".replace("  ", " ")


def start_befehl(a: AuftragRow, *, bins: dict[str, str] | None = None, resume: bool = False, nachfrage: str | None = None) -> str:
    """Shell-Befehl fuer den Start auf dem Host (rein, testbar): Worktree anlegen, Agent im Hintergrund."""
    p = _lauf_pfade(a)
    branch = a.branch or f"auftrag/{a.id}"
    text = prompt_fuer(a, resume=resume, nachfrage=nachfrage)
    if not resume:
        # Arbeitsverzeichnis ausdrücklich nennen – Agenten arbeiten sonst gelegentlich im Hauptrepo oder in eigenen Scratch-Ordnern
        text = f"Arbeitsverzeichnis (Git-Worktree, Branch {branch}): {p['worktree']}\nAlle Änderungen ausschließlich dort, nie außerhalb.\n\n{text}"
    lauf = agent_befehl(a, bins=bins or {}, text=text, resume=resume, pfade=p)
    wt = shlex.quote(p["worktree"])
    lauf_hinten = f"{lauf} > {shlex.quote(p['log'])} 2> {shlex.quote(p['stderr'])}; echo $? > {shlex.quote(p['done'])}"
    teile = [
        f"mkdir -p {shlex.quote(p['basis'])}",
        f"cd {shlex.quote(a.projekt)}",
        # Laufverzeichnis nie mit einchecken (neues git legt .git/info nicht an; Fehler hier sind unkritisch)
        f"{{ mkdir -p .git/info && {{ grep -qx '{LAUF_DIR}/' .git/info/exclude 2>/dev/null || echo '{LAUF_DIR}/' >> .git/info/exclude; }}; }} 2>/dev/null || true",
        f"{{ [ -d {wt} ] || git worktree add -B {shlex.quote(branch)} {wt} >/dev/null 2>&1 || git worktree add {wt} {shlex.quote(branch)} >/dev/null 2>&1; }}",
        f"printf '%s' {shlex.quote(text)} > {shlex.quote(p['prompt'])}",
        # Codex liest nur AGENTS.md, agy keins von beiden: die Konventionen des Repos (CLAUDE.md) beim Erststart anhängen
        (
            f"if [ {'0' if (resume or a.agent == 'claude') else '1'} = 1 ] && [ -f {wt}/CLAUDE.md ]; then "
            f"printf '\\n\\n--- Konventionen des Repos (CLAUDE.md, Auszug) ---\\n' >> {shlex.quote(p['prompt'])}; head -c 4000 {wt}/CLAUDE.md >> {shlex.quote(p['prompt'])}; fi"
        ),
        f"rm -f {shlex.quote(p['done'])}",
        # Abhängigkeiten des Hauptrepos in den Worktree verlinken (node_modules, .venv) – sonst scheitern Build, Tests und Qualitätstor
        f"for d in . frontend backend; do for m in node_modules .venv venv; do [ -d {shlex.quote(a.projekt)}/$d/$m ] && [ ! -e {wt}/$d/$m ] && ln -s {shlex.quote(a.projekt)}/$d/$m {wt}/$d/$m 2>/dev/null; done; done; true",
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
    """Liefert done-Code (oder leer), ob der Prozess lebt, Alter des Protokolls, dann die letzten Protokollzeilen."""
    p = _lauf_pfade(a)
    return (
        f"echo \"DONE=$(cat {shlex.quote(p['done'])} 2>/dev/null)\"; "
        f"pid=$(cat {shlex.quote(p['pid'])} 2>/dev/null); echo \"PID_LEBT=$([ -n \"$pid\" ] && kill -0 \"$pid\" 2>/dev/null && echo 1 || echo 0)\"; "
        f"echo \"LOG_ALTER=$(( $(date +%s) - $(stat -c %Y {shlex.quote(p['log'])} 2>/dev/null || date +%s) ))\"; "
        f"tail -n {int(zeilen)} {shlex.quote(p['log'])} 2>/dev/null; echo '---STDERR---'; tail -n 5 {shlex.quote(p['stderr'])} 2>/dev/null"
    )


def stand_werte(roh: str) -> dict:
    """DONE/PID_LEBT/LOG_ALTER aus der Stand-Ausgabe (rein, testbar)."""
    out: dict = {"done": None, "pid_lebt": None, "log_alter": None}
    m = re.search(r"^DONE=(\S*)$", roh, re.M)
    if m and m.group(1):
        out["done"] = m.group(1)
    m = re.search(r"^PID_LEBT=([01])$", roh, re.M)
    if m:
        out["pid_lebt"] = m.group(1) == "1"
    m = re.search(r"^LOG_ALTER=(\d+)$", roh, re.M)
    if m:
        out["log_alter"] = int(m.group(1))
    return out


def aufraeumen_befehl(a: AuftragRow, branch_loeschen: bool = False) -> str:
    """Worktree entfernen (Branch bleibt bis zum Merge, außer ausdrücklich gewünscht)."""
    p = _lauf_pfade(a)
    branch = a.branch or f"auftrag/{a.id}"
    teile = [
        f"cd {shlex.quote(a.projekt)}",
        f"git worktree remove --force {shlex.quote(p['worktree'])} 2>/dev/null; rm -rf {shlex.quote(p['worktree'])}; git worktree prune",
    ]
    if branch_loeschen:
        teile.append(f"git branch -D {shlex.quote(branch)} 2>/dev/null")
    teile.append("echo aufgeraeumt")
    return " && ".join(teile[:1]) + " && " + "; ".join(teile[1:])


# Dateien, die Commit-Hooks des Nutzers (graphify) im Worktree neu erzeugen – gehören nicht in den Abschluss-Commit
HOOK_ARTEFAKTE = ("ARCHITEKTUR.md", "ARCHITECTURE.md", "graphify-out")


def abschluss_befehl(a: AuftragRow) -> str:
    """Aenderungen im Worktree committen (ohne Hook-Artefakte, ohne eigene Hooks) und Kennzahlen des Diffs liefern."""
    p = _lauf_pfade(a)
    msg = f"auftrag {a.id}: {a.titel}"[:120]
    ausnahmen = " ".join(shlex.quote(f":!{x}") for x in HOOK_ARTEFAKTE)
    zuruecksetzen = " ".join(shlex.quote(x) for x in HOOK_ARTEFAKTE)
    return (
        f"cd {shlex.quote(p['worktree'])} && [ \"$(git rev-parse --show-toplevel 2>/dev/null)\" = {shlex.quote(p['worktree'])} ] && "
        f"{{ git checkout -q -- {zuruecksetzen} 2>/dev/null || true; }} && git add -A -- . {ausnahmen} && "
        f"(git diff --cached --quiet || git -c core.hooksPath=/dev/null -c user.name=cockpit -c user.email=cockpit@flowaudit.de commit -q -m {shlex.quote(msg)}) ; "
        "echo \"COMMITS=$(git rev-list --count HEAD ^$(git merge-base HEAD $(git rev-parse --abbrev-ref HEAD@{upstream} 2>/dev/null || echo master) 2>/dev/null || echo HEAD) 2>/dev/null)\"; "
        "echo \"HEAD=$(git rev-parse --short HEAD)\"; "
        "if [ \"$(git rev-list --count master..HEAD 2>/dev/null || echo 0)\" -gt 0 ]; then git diff --shortstat master HEAD 2>/dev/null | head -1; else echo 'keine Änderungen im Branch'; fi"
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


def _agy_zeile(d: dict) -> dict | None:
    """Antigravity CLI (agy) stream-json: event init / step_update (tool, agent_response) / result."""
    ev = d.get("event")
    if ev == "init":
        return {"ts": None, "art": "system", "text": f"agy-Sitzung {str(d.get('conversation_id', ''))[:8]} · Modus {(d.get('init') or {}).get('permission_mode', '?')}"}
    if ev == "step_update":
        su = d.get("step_update") or {}
        if su.get("step_type") == "tool" and su.get("state") == "ACTIVE":
            params = ((su.get("tool_info") or {}).get("parameters") or {})
            kurz = params.get("CommandLine") or params.get("AbsolutePath") or params.get("Pattern") or params.get("Query") or json.dumps(params, ensure_ascii=False)
            return {"ts": None, "art": "tool", "text": f"{su.get('tool_name')}: {str(kurz)[:200]}"}
        text = su.get("text") or su.get("delta") or su.get("content")
        if su.get("step_type") == "agent_response" and isinstance(text, str) and text.strip():
            return {"ts": None, "art": "text", "text": text.strip()[:1500]}
        return None
    if ev == "result":
        r = d.get("result") or {}
        u = r.get("usage") or {}
        status = str(r.get("status") or "")
        if status in ("CANCELED", "FAILED", "ERROR") and not (r.get("response") or "").strip():
            return {"ts": None, "art": "fehler", "text": f"agy: {status} ohne Antwort (Werkzeugfreigabe fehlt? Regeln in ~/.gemini/antigravity-cli/settings.json)"}
        return {"ts": None, "art": "result", "text": f"{str(r.get('response') or '').strip()[:3000]}  ·  {u.get('output_tokens', 0)} Ausgabe-Tokens"}
    return None


def _gemini_zeile(d: dict) -> dict | None:
    """Gemini CLI stream-json (Format variiert je Version) bzw. agy: Text, Werkzeuge, Ergebnis generisch."""
    if "event" in d and ("step_update" in d or "init" in d or "result" in d):
        return _agy_zeile(d)
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
    agy_usage: dict | None = None
    for line in roh.splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            d = json.loads(line)
        except ValueError:
            continue
        if d.get("event") == "result" and isinstance(d.get("result"), dict):
            r = d["result"]
            sid = r.get("conversation_id") or sid
            agy_usage = r.get("usage") or agy_usage
            antwort = str(r.get("response") or "").strip()
            if antwort:
                text = antwort
            elif str(r.get("status") or "") in ("CANCELED", "FAILED", "ERROR"):
                fehler = f"agy: {r.get('status')} ohne Antwort (Werkzeugfreigabe fehlt? Regeln in ~/.gemini/antigravity-cli/settings.json)"
            continue
        if d.get("event") == "init":
            sid = d.get("conversation_id") or sid
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
    if agy_usage is not None:
        return {"ergebnis": text, "fehler": fehler, "subtype": None, "kosten_usd": None,
                "tokens_in": (agy_usage.get("input_tokens") or 0) + (agy_usage.get("cache_read_tokens") or 0) or None,
                "tokens_out": (agy_usage.get("output_tokens") or 0) + (agy_usage.get("thinking_tokens") or 0) or None,
                "turns": None, "session_id": sid, "dauer_ms": None}
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
        # Werkzeuge, die Claude ohne Freigabe nicht ausführen durfte (dontAsk/acceptEdits verweigern still)
        "verweigert": [
            str(d.get("tool_name") or d.get("tool") or "?")
            + (f"({str((d.get('tool_input') or {}).get('command') or '')[:60]})" if isinstance(d.get("tool_input"), dict) and (d.get("tool_input") or {}).get("command") else "")
            for d in (letztes.get("permission_denials") or []) if isinstance(d, dict)
        ],
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


def agent_aufloesen(session: Session, a: AuftragRow, *, bins: dict[str, str], auslastung: dict | None = None) -> AuftragRow:
    """Wunsch „auto“ in einen konkreten Agenten überführen (einmalig beim ersten Start)."""
    from . import agent_wahl

    if a.agent != AGENT_AUTO:
        return a
    ausl = auslastung or {}
    typ = agent_wahl.aufgabentyp(a.titel, a.text, a.modus or "umsetzen", a.profil)
    verfuegbar = {k: bool(bins.get(k)) for k in AGENTEN}
    agent, grund = agent_wahl.waehlen(typ, claude_5h=ausl.get("claude_5h"), claude_woche=ausl.get("claude_woche"), codex_woche=ausl.get("codex_woche"), verfuegbar=verfuegbar)
    return aendern(session, a, agent=agent, agent_auto=1, agent_grund=f"{typ}: {grund}")


def anspruch_nehmen(session: Session, a: AuftragRow, *, resume: bool = False) -> bool:
    """Atomar auf »laeuft« setzen – nur einer von Runner, Web und Telegram darf denselben Auftrag starten (rein DB-seitig)."""
    from sqlalchemy import update

    erlaubt = ("eingang", "geplant", "unterbrochen", "fehler", "abgebrochen") if not resume else ("freigabe", "rueckfrage", "fertig", "unterbrochen", "fehler", "laeuft")
    res = session.execute(
        update(AuftragRow).where(AuftragRow.id == a.id, AuftragRow.status.in_(erlaubt)).values(status="laeuft", aktualisiert=_iso())
    )
    session.commit()
    if res.rowcount != 1:
        session.refresh(a)
        return False
    session.refresh(a)
    return True


def starten(session: Session, a: AuftragRow, *, bins: dict[str, str], resume: bool = False, nachfrage: str | None = None, auslastung: dict | None = None) -> AuftragRow:
    if not anspruch_nehmen(session, a, resume=resume):
        log.info("Auftrag %s: Start übersprungen, Status ist %s (anderer Starter war schneller)", a.id, a.status)
        return a
    a = agent_aufloesen(session, a, bins=bins, auslastung=auslastung)
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


# ---------------------------------------------------------------------------
# Qualitätstor: Prüfbefehle des Projekts im Worktree (.cockpit.yaml oder Erkennung), danach PR per gh
# ---------------------------------------------------------------------------

PRUEFUNG_ZEITLIMIT_S = 900
PRUEFUNG_STANDARD: dict[str, list[str]] = {
    # Erkennung über Manifestdateien, wenn keine .cockpit.yaml vorliegt
    "pyproject.toml": ["ruff check .", "python3 -m pytest -q"],
    "backend/requirements.txt": ["cd backend && python3 -m pytest -q"],
    "frontend/package.json": ["cd frontend && npm run type-check && npm run build"],
    "package.json": ["npm run build"],
}


def pruefung_lesen_befehl(a: AuftragRow, basis: str = "master") -> str:
    """Prüfbefehle stammen aus dem Basis-Commit (`git show <basis>:.cockpit.yaml`), nicht aus dem Worktree –
    sonst könnte ein Schreibagent seine eigenen Prüfbefehle setzen und beliebige Host-Kommandos auslösen."""
    p = _lauf_pfade(a)
    wt = shlex.quote(p["worktree"])
    return (
        f"cd {wt} && echo '---COCKPIT_YAML---'; "
        f"(git show {shlex.quote(basis)}:.cockpit.yaml 2>/dev/null || git show origin/{shlex.quote(basis)}:.cockpit.yaml 2>/dev/null || git show main:.cockpit.yaml 2>/dev/null); "
        "echo '---MANIFESTE---'; "
        "for f in pyproject.toml backend/requirements.txt frontend/package.json package.json .github/workflows; do [ -e \"$f\" ] && echo \"$f\"; done; "
        "echo '---PYTEST---'; (ls tests 2>/dev/null | head -1 || ls backend/tests 2>/dev/null | head -1)"
    )


def pruefbefehle_aus(roh: str) -> tuple[list[str], str]:
    """Prüfbefehle und Basis-Branch aus der Ausgabe von pruefung_lesen_befehl (rein, testbar).

    .cockpit.yaml: einfache Form ohne YAML-Bibliothek – Zeilen `basis: master` und unter `pruefung:` je `- befehl`.
    """
    yaml_teil = roh.split("---COCKPIT_YAML---", 1)[1].split("---MANIFESTE---", 1)[0] if "---COCKPIT_YAML---" in roh else ""
    manifeste = roh.split("---MANIFESTE---", 1)[1].split("---PYTEST---", 1)[0].split() if "---MANIFESTE---" in roh else []
    basis = "master"
    befehle: list[str] = []
    in_pruefung = False
    for line in yaml_teil.splitlines():
        st = line.strip()
        if not st or st.startswith("#"):
            continue
        if st.startswith("basis:"):
            basis = st.split(":", 1)[1].strip().strip("'\"") or basis
            in_pruefung = False
        elif st.startswith("pruefung:"):
            in_pruefung = True
        elif in_pruefung and st.startswith("- "):
            befehle.append(st[2:].strip().strip("'\""))
        elif not line.startswith((" ", "\t")):
            in_pruefung = False
    if not befehle:
        for manifest, standard in PRUEFUNG_STANDARD.items():
            if manifest in manifeste:
                befehle.extend(standard)
        if "backend/requirements.txt" in manifeste and "pyproject.toml" in manifeste:
            befehle = [b for b in befehle if not b.startswith("python3 -m pytest")]
    return befehle, basis


def pruefung_befehl(a: AuftragRow, befehle: list[str]) -> str:
    """Prüfbefehle nacheinander im Worktree ausführen; je Befehl Marker mit Exit-Code und Dauer, Ausgabe gekürzt."""
    p = _lauf_pfade(a)
    teile = [f"cd {shlex.quote(p['worktree'])}"]
    for i, b in enumerate(befehle):
        teile.append(
            f"echo '---PRUEF {i}---'; s=$(date +%s); (timeout {PRUEFUNG_ZEITLIMIT_S} bash -lc {shlex.quote(b)}) 2>&1 | tail -n 25; "
            f"rc=${{PIPESTATUS[0]}}; echo \"---ENDE {i} rc=$rc dauer=$(( $(date +%s) - s ))---\""
        )
    return " ; ".join(teile)


def pruefung_auswerten(roh: str, befehle: list[str]) -> tuple[list[dict], bool]:
    """Marker der Prüfausgabe → [{befehl, ok, dauer_s, auszug}], gesamt_ok (rein, testbar)."""
    out: list[dict] = []
    for i, b in enumerate(befehle):
        m = re.search(rf"---PRUEF {i}---\n(.*?)---ENDE {i} rc=(\d+) dauer=(\d+)---", roh, re.S)
        if not m:
            out.append({"befehl": b, "ok": False, "dauer_s": None, "auszug": "keine Ausgabe (Zeitlimit oder Abbruch)"})
            continue
        auszug = m.group(1).strip()
        out.append({"befehl": b, "ok": m.group(2) == "0", "dauer_s": int(m.group(3)), "auszug": auszug[-1200:]})
    return out, bool(out) and all(x["ok"] for x in out)


def pruefen(session: Session, a: AuftragRow) -> AuftragRow:
    """Qualitätstor: Prüfbefehle im Worktree laufen lassen und Ergebnis an der Karte speichern (mergt nie)."""
    host = host_fuer(session, a.host)
    if host is None or not a.worktree:
        return a
    try:
        roh = run_on_host(host, pruefung_lesen_befehl(a), timeout=20).stdout or ""
        befehle, _basis = pruefbefehle_aus(roh)
        if not befehle:
            return aendern(session, a, pruefung=json.dumps([{"befehl": "–", "ok": True, "dauer_s": 0, "auszug": "keine Prüfbefehle gefunden (.cockpit.yaml oder Manifest)"}], ensure_ascii=False), pruefung_ok=None)
        res = run_on_host(host, pruefung_befehl(a, befehle), timeout=PRUEFUNG_ZEITLIMIT_S * len(befehle) + 30)
        ergebnisse, ok = pruefung_auswerten(res.stdout or "", befehle)
    except Exception as exc:  # noqa: BLE001
        log.warning("Auftrag %s Prüfung: %s", a.id, exc)
        ergebnisse, ok = [{"befehl": "–", "ok": False, "dauer_s": None, "auszug": str(exc)[:300]}], False
    return aendern(session, a, pruefung=json.dumps(ergebnisse, ensure_ascii=False), pruefung_ok=1 if ok else 0)


def pr_befehl(a: AuftragRow, basis: str, titel: str, body_pfad: str) -> str:
    """Branch pushen und PR per gh anlegen (Body aus Datei); liefert die PR-URL."""
    p = _lauf_pfade(a)
    branch = a.branch or f"auftrag/{a.id}"
    return (
        f"cd {shlex.quote(p['worktree'])} && git push -u origin {shlex.quote(branch)} 2>&1 | tail -n 2 && "
        f"gh pr create --base {shlex.quote(basis)} --head {shlex.quote(branch)} --title {shlex.quote(titel[:200])} --body-file {shlex.quote(body_pfad)} 2>&1 | tail -n 3"
    )


def pr_body(a: AuftragRow) -> str:
    zeilen = [f"Auftrag `{a.id}` aus dem Cockpit-Kanban · Agent {a.agent} · Profil {a.profil}", "", "## Ergebnis des Agenten", "", (a.ergebnis or "–")[:6000], ""]
    if a.pruefung:
        try:
            pr = json.loads(a.pruefung)
        except ValueError:
            pr = []
        zeilen += ["## Prüfung im Worktree (Cockpit)", ""]
        for x in pr:
            zeilen.append(f"- {'✅' if x.get('ok') else '❌'} `{x.get('befehl')}`" + (f" ({x.get('dauer_s')} s)" if x.get("dauer_s") is not None else ""))
        zeilen.append("")
    zeilen.append("Das Cockpit prüft, mergt aber nicht – Merge nach Durchsicht auf GitHub.")
    return "\n".join(zeilen)


def pr_erstellen(session: Session, a: AuftragRow) -> AuftragRow:
    """Pull Request per gh anlegen (Branch wird gepusht); nie mergen."""
    host = host_fuer(session, a.host)
    if host is None or not a.branch:
        return aendern(session, a, fehler="Kein Host oder Branch für den PR")
    p = _lauf_pfade(a)
    body_pfad = f"{p['basis']}/pr_body.md"
    try:
        roh = run_on_host(host, pruefung_lesen_befehl(a), timeout=20).stdout or ""
        _befehle, basis = pruefbefehle_aus(roh)
        run_on_host(host, f"mkdir -p {shlex.quote(p['basis'])} && printf '%s' {shlex.quote(pr_body(a))} > {shlex.quote(body_pfad)}", timeout=20)
        res = run_on_host(host, pr_befehl(a, basis, a.titel, body_pfad), timeout=120)
        out = (res.stdout or "") + (res.stderr or "")
        m = re.search(r"https://github\.com/\S+/pull/\d+", out)
        if not m:
            return aendern(session, a, fehler=f"PR nicht angelegt: {out.strip()[-300:]}")
        return aendern(session, a, pr_url=m.group(0), fehler=None, letzte_zeile=f"PR {m.group(0).rsplit('/', 1)[-1]} angelegt")
    except Exception as exc:  # noqa: BLE001
        return aendern(session, a, fehler=f"PR nicht angelegt: {str(exc)[:300]}")


def pr_checks_befehl(a: AuftragRow) -> str:
    p = _lauf_pfade(a)
    return f"cd {shlex.quote(a.projekt)} && gh pr checks {shlex.quote(a.pr_url or '')} 2>&1 | tail -n 12; cd {shlex.quote(p['worktree'])} 2>/dev/null; true"


def pr_checks_kurz(roh: str) -> str:
    """Ausgabe von `gh pr checks` → Kurzstand (rein, testbar): z. B. »2 grün · 1 rot · 1 läuft« oder »keine Checks«."""
    gruen = rot = laeuft = 0
    for line in roh.splitlines():
        st = line.strip().lower()
        if not st or st.startswith("no checks"):
            continue
        if "\tpass" in st or "\tsuccess" in st or " pass\t" in st or "✓" in st:
            gruen += 1
        elif "\tfail" in st or " fail\t" in st or "✗" in st or "\tfailure" in st:
            rot += 1
        elif "\tpending" in st or "queued" in st or "in_progress" in st or "*" in st.split("\t")[0]:
            laeuft += 1
    if not (gruen or rot or laeuft):
        return "keine Checks"
    teile = [f"{gruen} grün"] if gruen else []
    if rot:
        teile.append(f"{rot} rot")
    if laeuft:
        teile.append(f"{laeuft} läuft")
    return " · ".join(teile)


UNTERBROCHEN_PROMPT = (
    "Der vorherige Lauf wurde unterbrochen (Neustart oder Zeitlimit). Prüfe zuerst den Stand im Worktree "
    "(`git status`, `git diff`, letzte Commits) und setze die Arbeit am Auftrag genau dort fort, wo sie stehen geblieben ist. "
    "Wiederhole nichts, was schon erledigt ist."
)


def stand_pruefen(session: Session, a: AuftragRow, github_url: str | None = None, max_dauer_s: int | None = None) -> AuftragRow:
    """Protokoll des laufenden Auftrags lesen; bei Ende Ergebnis uebernehmen und committen.

    Ohne Ende-Marke und ohne lebenden Prozess (Neustart des Hosts) oder nach Überschreiten von
    ``max_dauer_s`` gilt der Lauf als *unterbrochen* – Worktree und Sitzung bleiben, Fortsetzen ist möglich.
    """
    host = host_fuer(session, a.host)
    if host is None:
        return a
    try:
        res = run_on_host(host, stand_befehl(a, 120), timeout=25)
    except Exception as exc:  # noqa: BLE001
        log.warning("Auftrag %s Stand: %s", a.id, exc)
        return a
    roh = res.stdout or ""
    werte = stand_werte(roh)
    done = werte["done"]
    stderr_teil = roh.split("---STDERR---", 1)[1].strip() if "---STDERR---" in roh else ""
    zeilen = log_zeilen(roh, max_zeilen=3, agent=a.agent)
    letzte = zeilen[-1]["text"] if zeilen else a.letzte_zeile
    gestartet = datetime.fromisoformat(a.gestartet.replace("Z", "+00:00")) if a.gestartet else datetime.now(UTC)
    dauer = int((datetime.now(UTC) - gestartet).total_seconds())
    if done is None:
        sitzung = (ergebnis_aus_log(roh, agent=a.agent) or {}).get("session_id") or a.session_id
        if werte["pid_lebt"] is False:
            log.warning("Auftrag %s: Prozess verschwunden (Neustart?)", a.id)
            return aendern(session, a, status="unterbrochen", session_id=sitzung, beendet=_iso(), dauer_s=dauer,
                           fehler="Prozess verschwunden (Neustart des Hosts?) – Fortsetzen möglich", letzte_zeile="unterbrochen")
        if max_dauer_s and dauer > max_dauer_s:
            log.warning("Auftrag %s: Zeitlimit %d s überschritten – wird beendet", a.id, max_dauer_s)
            try:
                run_on_host(host, stopp_befehl(a), timeout=20)
            except Exception as exc:  # noqa: BLE001
                log.warning("Auftrag %s stoppen: %s", a.id, exc)
            return aendern(session, a, status="unterbrochen", session_id=sitzung, beendet=_iso(), dauer_s=dauer,
                           fehler=f"Zeitlimit von {max_dauer_s // 60} min überschritten – Fortsetzen möglich", letzte_zeile="Zeitlimit")
        return aendern(session, a, letzte_zeile=(letzte or "")[:200], dauer_s=dauer, session_id=sitzung)
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
        if not (ab.stdout or "").strip():
            felder["fehler"] = "Abschluss im Worktree fehlgeschlagen (kein Ergebnis) – Änderungen ggf. nicht committet"
        kopf = re.search(r"HEAD=(\w+)", ab.stdout or "")
        felder["letzte_zeile"] = (ab.stdout or "").strip().splitlines()[-1][:200] if (ab.stdout or "").strip() else "fertig"
        if kopf and github_url:
            felder["diff_url"] = diff_url(github_url, "master", a.branch or f"auftrag/{a.id}")
    except Exception as exc:  # noqa: BLE001
        log.warning("Auftrag %s Abschluss: %s", a.id, exc)
    felder["status"] = status_nach_erfolg(a, felder.get("ergebnis"))
    verweigert = erg.get("verweigert") or []
    if verweigert and felder["status"] == "fertig":
        # Claude hat Werkzeuge ohne Freigabe nicht ausführen dürfen – als Rückfrage „Berechtigung“ zeigen
        felder["status"] = "rueckfrage"
        felder["ergebnis"] = "Berechtigung verweigert für: " + ", ".join(verweigert[:6]) + " – Profil erhöhen und fortsetzen?\n\n" + (felder.get("ergebnis") or "")
        felder["letzte_zeile"] = "Rückfrage: Berechtigung"
    if felder["status"] == "freigabe":
        felder["letzte_zeile"] = "Plan liegt vor – Freigabe im Kanban"
    a = aendern(session, a, **felder)
    # Qualitätstor: nach einer Umsetzung (nicht nach Bericht/Plan) die Prüfbefehle des Projekts im Worktree laufen lassen
    if a.status == "fertig" and phase(a) == "umsetzung" and a.worktree:
        a = pruefen(session, a)
    return a


def fortsetzen(session: Session, a: AuftragRow, *, bins: dict[str, str]) -> AuftragRow:
    """Unterbrochenen Lauf fortsetzen: mit Sitzung per Resume, sonst neuer Lauf im bestehenden Worktree."""
    a = aendern(session, a, fehler=None, beendet=None)
    if a.session_id:
        return starten(session, a, bins=bins, resume=True, nachfrage=UNTERBROCHEN_PROMPT)
    return starten(session, a, bins=bins)


def aufraeumen(session: Session, a: AuftragRow, *, branch_loeschen: bool = False) -> AuftragRow:
    """Worktree (und optional Branch) auf dem Host entfernen; Karte bleibt mit Ergebnis erhalten."""
    host = host_fuer(session, a.host)
    if host is not None and (a.worktree or a.branch):
        try:
            run_on_host(host, aufraeumen_befehl(a, branch_loeschen=branch_loeschen), timeout=40)
        except Exception as exc:  # noqa: BLE001
            log.warning("Auftrag %s aufräumen: %s", a.id, exc)
    return aendern(session, a, worktree=None, branch=None if branch_loeschen else a.branch, letzte_zeile="Worktree aufgeräumt" + (" · Branch gelöscht" if branch_loeschen else ""))


def umsetzen(session: Session, a: AuftragRow, *, bins: dict[str, str], hinweis: str | None = None) -> AuftragRow:
    """Freigabe eines Plans: Sitzung fortsetzen, jetzt mit Schreibprofil."""
    a = aendern(session, a, freigegeben=_iso(), text=f"{a.text}\n\n--- Freigabe ---\n{umsetzungstext(hinweis)}")
    return starten(session, a, bins=bins, resume=True, nachfrage=umsetzungstext(hinweis))
