"""Telegram-Dialog: Rückfragen, Freigaben, Unterbrechungen und Ergebnisse der Agenten vom Handy aus bedienen.

Nur die Instanz mit aktivem Push (Leitinstanz) holt Updates per Long-Polling (``getUpdates``).
Jede Nachricht des Cockpits trägt Schaltflächen (Inline-Keyboard); ``callback_data`` ist mit dem
Vault-Schlüssel der Instanz signiert (HMAC, Ablauf 7 Tage). Antwortet der Nutzer *auf* eine
Cockpit-Nachricht, gehört der Text zum zugehörigen Auftrag (Tabelle ``cockpit_telegram``).
Kommandos ohne Auftragsbezug: /status, /auftraege, /neu, /vorschlaege, /plan, /stop, /pause,
/weiter, /hilfe. Absender außerhalb der Whitelist (Chat-ID des Vaults, optional Nutzer-IDs)
werden still verworfen und im Audit-Log vermerkt.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import logging
import time
from datetime import UTC, datetime

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..crud import audit as crud_audit
from ..db import get_session_factory
from ..models import TelegramNachrichtRow
from . import auftraege as svc
from . import kurzfassung
from . import wall_config as wc

log = logging.getLogger(__name__)

API = "https://api.telegram.org/bot{token}/{method}"
ABLAUF_S = 7 * 86400
MAX_TEXT = 3900

# Schaltflächen je Status: (Beschriftung, Aktion)
TASTATUREN: dict[str, list[list[tuple[str, str]]]] = {
    "freigabe": [[("✅ Freigeben", "freigeben"), ("✏️ Mit Hinweis", "hinweis")], [("📄 Ganzer Plan", "plan"), ("🗑 Nur Bericht", "bericht")]],
    "rueckfrage": [[("Ja", "ja"), ("Nein", "nein")], [("✏️ Antworten", "antworten"), ("⏹ Stopp", "stopp")]],
    "unterbrochen": [[("▶ Fortsetzen", "fortsetzen"), ("🗑 Verwerfen", "verwerfen")]],
    "fertig": [[("🔗 PR erstellen", "pr"), ("🧹 Worktree aufräumen", "aufraeumen")]],
    "fehler": [[("↩ Erneut in Eingang", "eingang"), ("🗑 Löschen", "loeschen")]],
}
SYMBOLE = {"freigabe": "📋", "rueckfrage": "❓", "unterbrochen": "⏸", "fertig": "✅", "fehler": "🔴", "abgebrochen": "⏹"}
HILFE = (
    "Cockpit-Kommandos:\n"
    "/status – Kontingente und laufende Aufträge\n"
    "/auftraege – offene Karten je Spalte\n"
    "/neu <projekt> <auftragstext> – Karte in den Eingang\n"
    "/vorschlaege <projekt> – Vorschlagslauf anstoßen\n"
    "/plan <id> – ganzen Plan/Ergebnistext senden\n"
    "/stop <id> – laufenden Auftrag beenden\n"
    "/pause · /weiter – Runner anhalten / fortsetzen\n"
    "Antworte auf eine Cockpit-Nachricht, um dem Auftrag zu antworten oder einen Hinweis zur Freigabe zu geben."
)


# ---------------------------------------------------------------------------
# Signierte Schaltflächen (rein, testbar)
# ---------------------------------------------------------------------------


def _sig(key: str, teile: str) -> str:
    return hmac.new(key.encode("utf-8"), teile.encode("utf-8"), hashlib.sha256).hexdigest()[:16]


def callback_data(aktion: str, auftrag_id: str, key: str, jetzt: float | None = None) -> str:
    ablauf = int((jetzt or time.time()) + ABLAUF_S)
    teile = f"{aktion}:{auftrag_id}:{ablauf}"
    return f"{teile}:{_sig(key, teile)}"


def callback_pruefen(data: str, key: str, jetzt: float | None = None) -> tuple[str, str] | None:
    """(aktion, auftrag_id) oder None bei falscher Signatur / abgelaufen (Telegram erlaubt ≤ 64 Byte – passt)."""
    try:
        aktion, auftrag_id, ablauf, sig = data.split(":", 3)
        ablauf_i = int(ablauf)
    except ValueError:
        return None
    if ablauf_i < (jetzt or time.time()):
        return None
    if not hmac.compare_digest(_sig(key, f"{aktion}:{auftrag_id}:{ablauf}"), sig):
        return None
    return aktion, auftrag_id


def tastatur(status: str, auftrag_id: str, key: str, *, pr_vorhanden: bool = False) -> dict | None:
    zeilen = TASTATUREN.get(status)
    if not zeilen:
        return None
    if status == "fertig" and pr_vorhanden:
        zeilen = [[("🧹 Worktree aufräumen", "aufraeumen")]]
    return {"inline_keyboard": [[{"text": t, "callback_data": callback_data(a, auftrag_id, key)} for t, a in zeile] for zeile in zeilen]}


def kommando_parsen(text: str) -> tuple[str, list[str]] | None:
    """'/neu cockpit Mach X' → ('neu', ['cockpit', 'Mach X']); None wenn kein Kommando (rein, testbar)."""
    t = (text or "").strip()
    if not t.startswith("/"):
        return None
    kopf, _, rest = t.partition(" ")
    name = kopf[1:].split("@", 1)[0].lower()
    if name in ("neu", "vorschlaege", "vorschläge"):
        proj, _, auftrag = rest.strip().partition(" ")
        return ("vorschlaege" if name.startswith("vorschl") else "neu", [proj.strip(), auftrag.strip()])
    return name, ([rest.strip()] if rest.strip() else [])


def nachrichtentext(a, kurz: str, kanban_url: str | None, pruefung_text: str | None = None) -> str:
    sym = SYMBOLE.get(a.status, "•")
    kopf = {"freigabe": "Plan liegt vor – Freigabe?", "rueckfrage": "Rückfrage des Agenten", "unterbrochen": "Lauf unterbrochen",
            "fertig": "Auftrag fertig", "fehler": "Auftrag fehlgeschlagen", "abgebrochen": "Auftrag abgebrochen"}.get(a.status, a.status)
    zeilen = [f"{sym} {kopf}", f"{a.titel}", f"{a.projekt_name} · {a.agent} · {a.id}"]
    if a.status == "unterbrochen" and a.fehler:
        zeilen.append(a.fehler[:200])
    if a.status == "fehler" and a.fehler:
        zeilen.append(a.fehler[:300])
    if kurz:
        zeilen += ["", kurz]
    if pruefung_text:
        zeilen += ["", pruefung_text]
    if a.status == "fertig" and a.dauer_s:
        zeilen.append(f"Dauer {a.dauer_s // 60} min {a.dauer_s % 60} s" + (f" · {a.kosten_usd:.2f} $" if a.kosten_usd else ""))
    if a.diff_url and a.status == "fertig":
        zeilen.append(a.diff_url)
    if kanban_url:
        zeilen.append(kanban_url)
    return "\n".join(zeilen)[:MAX_TEXT]


def pruefung_kurz(a) -> str | None:
    if not a.pruefung:
        return None
    try:
        pr = json.loads(a.pruefung)
    except ValueError:
        return None
    if not pr:
        return None
    if a.pruefung_ok is None:
        return "Prüfung: keine Prüfbefehle gefunden"
    rot = [x.get("befehl") for x in pr if not x.get("ok")]
    return "Prüfung ✅ alle Befehle grün" if not rot else "Prüfung ❌ rot: " + ", ".join(str(r) for r in rot[:3])


# ---------------------------------------------------------------------------
# Telegram-Aufrufe
# ---------------------------------------------------------------------------


async def _api(token: str, method: str, **params) -> dict | None:
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(40.0, connect=10.0)) as c:
            resp = await c.post(API.format(token=token, method=method), json=params)
        if resp.status_code >= 400:
            log.warning("Telegram %s: HTTP %s %s", method, resp.status_code, resp.text[:160])
            return None
        d = resp.json()
        return d.get("result") if d.get("ok") else None
    except (httpx.HTTPError, ValueError) as exc:
        log.warning("Telegram %s: %s", method, exc)
        return None


async def senden(token: str, chat_id: str, text: str, markup: dict | None = None) -> int | None:
    params: dict = {"chat_id": chat_id, "text": text[:MAX_TEXT], "disable_web_page_preview": True}
    if markup:
        params["reply_markup"] = markup
    r = await _api(token, "sendMessage", **params)
    return int(r["message_id"]) if isinstance(r, dict) and r.get("message_id") else None


async def _tastatur_entfernen(token: str, chat_id: str, message_id: int) -> None:
    await _api(token, "editMessageReplyMarkup", chat_id=chat_id, message_id=message_id, reply_markup={"inline_keyboard": []})


# ---------------------------------------------------------------------------
# Ereignisse des Runners → Nachricht mit Schaltflächen
# ---------------------------------------------------------------------------


def _zugang(session: Session, cfg: wc.WallConfig) -> tuple[str | None, str | None, dict]:
    from ..routes.overview import _secret_value

    pcfg = cfg.push or {}
    token = _secret_value(session, str(pcfg.get("token_secret") or "telegram_bot_token"))
    chat_id = _secret_value(session, str(pcfg.get("chat_secret") or "telegram_chat_id")) or str(pcfg.get("chat_id") or "")
    return token, chat_id, (pcfg.get("dialog") if isinstance(pcfg.get("dialog"), dict) else {})


def _key(session: Session) -> str:
    """HMAC-Schlüssel für Schaltflächen: der Vault-Schlüssel der Instanz, sonst ein einmal erzeugter Zufallswert in den Einstellungen."""
    k = None
    try:
        from ..config import load_config

        k = getattr(load_config(), "vault_key", None)
    except Exception as exc:  # noqa: BLE001
        log.warning("Telegram-Dialog: Konfiguration nicht lesbar (%s) – Schlüssel aus den Einstellungen", exc)
    if not k:
        k = str(wc.read_setting(session, "telegram_hmac_key", "") or "")
        if not k:
            k = hashlib.sha256(f"{time.time()}-{id(session)}".encode()).hexdigest()
            wc.write_setting(session, "telegram_hmac_key", k)
    return str(k)


def _kanban_url(cfg: wc.WallConfig) -> str | None:
    wand = str((cfg.push or {}).get("wand_url") or "")
    return wand.replace("/admin/wall", "/admin/kanban") if wand else None


def _modell(cfg: wc.WallConfig) -> str | None:
    for m in cfg.chat_models or []:
        if m.get("tag"):
            return str(m["tag"])
    return None


async def ereignis_senden(session: Session, a, cfg: wc.WallConfig) -> bool:
    """Statuswechsel eines Auftrags als Dialognachricht (mit Schaltflächen) verschicken; merkt sich die message_id."""
    token, chat_id, dialog = _zugang(session, cfg)
    if not token or not chat_id or not dialog.get("aktiv", True):
        return False
    zweck = {"freigabe": "plan", "rueckfrage": "frage"}.get(a.status, "ergebnis")
    kurz = await kurzfassung.kuerzen(a.ergebnis if a.status != "fehler" else None, zweck, modell=_modell(cfg), aktiv=bool(dialog.get("kuerzen", True)))
    text = nachrichtentext(a, kurz, _kanban_url(cfg), pruefung_kurz(a) if a.status == "fertig" else None)
    mid = await senden(token, chat_id, text, tastatur(a.status, a.id, _key(session), pr_vorhanden=bool(a.pr_url)))
    if mid is None:
        return False
    session.add(TelegramNachrichtRow(message_id=mid, chat_id=str(chat_id), auftrag_id=a.id, art=a.status, erstellt=datetime.now(UTC).isoformat(timespec="seconds")))
    session.commit()
    return True


# ---------------------------------------------------------------------------
# Eingehende Updates
# ---------------------------------------------------------------------------


def _erlaubt(update_from: dict | None, chat: dict | None, chat_id: str, dialog: dict) -> bool:
    if not chat or str(chat.get("id")) != str(chat_id):
        return False
    erlaubt = [str(x) for x in (dialog.get("erlaubte_user_ids") or [])]
    if erlaubt and str((update_from or {}).get("id")) not in erlaubt:
        return False
    return True


def _auftrag_zu_nachricht(session: Session, chat_id: str, message_id: int):
    row = session.execute(select(TelegramNachrichtRow).where(TelegramNachrichtRow.chat_id == str(chat_id), TelegramNachrichtRow.message_id == int(message_id))).scalar_one_or_none()
    return svc.holen(session, row.auftrag_id) if row else None


def _bins(cfg: wc.WallConfig) -> dict:
    return {**cfg.agent_bins, "codex_sandbox": cfg.codex_sandbox}


def _pending_lesen(session: Session, chat_id: str) -> dict | None:
    p = wc.read_setting(session, "telegram_pending", {}) or {}
    e = p.get(str(chat_id))
    if e and e.get("ablauf", 0) > time.time():
        return e
    return None


def _pending_setzen(session: Session, chat_id: str, eintrag: dict | None) -> None:
    p = wc.read_setting(session, "telegram_pending", {}) or {}
    if eintrag:
        p[str(chat_id)] = {**eintrag, "ablauf": time.time() + 1800}
    else:
        p.pop(str(chat_id), None)
    wc.write_setting(session, "telegram_pending", p)


async def _aktion(session: Session, cfg: wc.WallConfig, aktion: str, a, token: str, chat_id: str, user: str) -> str:
    """Schaltfläche ausführen; liefert die Kurzantwort für answerCallbackQuery / Bestätigung."""
    bins = _bins(cfg)
    try:
        if aktion == "freigeben":
            if a.status != "freigabe":
                return f"Auftrag ist {a.status}, nicht in Freigabe"
            await asyncio.to_thread(svc.umsetzen, session, a, bins=bins)
            antwort = "Freigegeben – Umsetzung läuft"
        elif aktion == "hinweis":
            _pending_setzen(session, chat_id, {"art": "hinweis", "auftrag_id": a.id})
            return "Schreib deinen Hinweis als nächste Nachricht"
        elif aktion == "plan":
            text = a.ergebnis or "(kein Text)"
            for i in range(0, min(len(text), 4 * MAX_TEXT), MAX_TEXT):
                await senden(token, chat_id, text[i : i + MAX_TEXT])
            return "Plan gesendet"
        elif aktion == "bericht":
            if a.status != "freigabe":
                return f"Auftrag ist {a.status}"
            svc.aendern(session, a, status="fertig", letzte_zeile="nur Bericht behalten")
            antwort = "Als Bericht abgelegt"
        elif aktion in ("ja", "nein"):
            if a.status != "rueckfrage":
                return f"Auftrag ist {a.status}, keine Rückfrage offen"
            await asyncio.to_thread(svc.starten, session, a, bins=bins, resume=True, nachfrage="Ja." if aktion == "ja" else "Nein.")
            antwort = f"„{'Ja' if aktion == 'ja' else 'Nein'}“ gesendet – Agent arbeitet weiter"
        elif aktion == "antworten":
            _pending_setzen(session, chat_id, {"art": "antwort", "auftrag_id": a.id})
            return "Schreib deine Antwort als nächste Nachricht"
        elif aktion == "stopp":
            if a.status != "laeuft":
                return f"Auftrag läuft nicht ({a.status})"
            await asyncio.to_thread(svc.stoppen, session, a)
            antwort = "Gestoppt"
        elif aktion == "fortsetzen":
            if a.status != "unterbrochen":
                return f"Auftrag ist {a.status}"
            await asyncio.to_thread(svc.fortsetzen, session, a, bins=bins)
            antwort = "Wird fortgesetzt"
        elif aktion == "verwerfen":
            svc.aendern(session, a, status="abgebrochen", beendet=svc._iso(), letzte_zeile="verworfen")
            antwort = "Verworfen"
        elif aktion == "pr":
            if a.pr_url:
                return f"PR existiert: {a.pr_url}"
            a = await asyncio.to_thread(svc.pr_erstellen, session, a)
            antwort = f"PR angelegt: {a.pr_url}" if a.pr_url else f"PR nicht angelegt: {(a.fehler or '')[:120]}"
        elif aktion == "aufraeumen":
            await asyncio.to_thread(svc.aufraeumen, session, a)
            antwort = "Worktree aufgeräumt"
        elif aktion == "eingang":
            svc.aendern(session, a, status="eingang", fehler=None, beendet=None, freigegeben=None)
            antwort = "Zurück im Eingang"
        elif aktion == "loeschen":
            session.delete(a)
            session.commit()
            antwort = "Gelöscht"
        else:
            return "Unbekannte Aktion"
    except Exception as exc:  # noqa: BLE001
        log.warning("Telegram-Aktion %s auf %s: %s", aktion, a.id, exc)
        return f"Fehler: {str(exc)[:120]}"
    crud_audit.write(session, action=f"auftrag.{aktion}", target=a.id, actor=f"telegram:{user}", after={"via": "telegram"})
    return antwort


async def _text_verarbeiten(session: Session, cfg: wc.WallConfig, msg: dict, token: str, chat_id: str, user: str) -> None:
    text = str(msg.get("text") or "").strip()
    if not text:
        return
    bins = _bins(cfg)
    # 1. Antwort auf eine Cockpit-Nachricht oder ausstehende Eingabe
    ziel = None
    reply = msg.get("reply_to_message")
    if isinstance(reply, dict) and reply.get("message_id"):
        ziel = _auftrag_zu_nachricht(session, chat_id, int(reply["message_id"]))
    pending = _pending_lesen(session, chat_id)
    if ziel is None and pending and not text.startswith("/"):
        ziel = svc.holen(session, str(pending.get("auftrag_id")))
    if ziel is not None and not text.startswith("/"):
        _pending_setzen(session, chat_id, None)
        if ziel.status == "freigabe":
            await asyncio.to_thread(svc.umsetzen, session, ziel, bins=bins, hinweis=text)
            antwort = f"Freigegeben mit Hinweis – Umsetzung von {ziel.id} läuft"
        elif ziel.status in ("rueckfrage", "fertig", "unterbrochen", "fehler"):
            if not ziel.session_id:
                antwort = "Keine Sitzung zum Fortsetzen – bitte im Kanban neu anlegen"
            else:
                svc.aendern(session, ziel, text=f"{ziel.text}\n\n--- Nachfrage (Telegram) ---\n{text}")
                await asyncio.to_thread(svc.starten, session, ziel, bins=bins, resume=True, nachfrage=text)
                antwort = f"Antwort an {ziel.id} gesendet – Agent arbeitet weiter"
        elif ziel.status == "laeuft":
            antwort = f"{ziel.id} läuft gerade – Antwort erst nach dem Zug möglich"
        else:
            antwort = f"{ziel.id} ist {ziel.status} – dort ist keine Antwort vorgesehen"
        crud_audit.write(session, action="auftrag.antwort", target=ziel.id, actor=f"telegram:{user}", after={"text": text[:300]})
        await senden(token, chat_id, antwort)
        return
    # 2. Kommandos
    k = kommando_parsen(text)
    if not k:
        await senden(token, chat_id, "Antworte auf eine Cockpit-Nachricht oder nutze /hilfe.")
        return
    name, args = k
    from . import auftrag_runner as runner

    if name in ("hilfe", "help", "start"):
        await senden(token, chat_id, HILFE)
    elif name == "status":
        kap = runner.kapazitaet(session)
        zeilen = [f"Läuft {kap['laufend']} / max {kap['parallel_max']}" + (f" · {kap['pause_grund']}" if kap.get("pause_grund") else "")]
        if kap.get("fuenf_stunden_pct") is not None:
            zeilen.append(f"Claude 5 h {int(kap['fuenf_stunden_pct'])} % · Woche {int(kap['woche_pct'] or 0)} %")
        if kap.get("codex_woche_pct") is not None:
            zeilen.append(f"Codex Woche {int(kap['codex_woche_pct'])} %")
        await senden(token, chat_id, "\n".join(zeilen))
    elif name in ("auftraege", "aufträge"):
        rows = [x for x in svc.liste(session) if x.status not in ("fertig", "abgebrochen")]
        if not rows:
            await senden(token, chat_id, "Keine offenen Aufträge.")
        else:
            await senden(token, chat_id, "\n".join(f"{SYMBOLE.get(x.status, '•')} {x.status}: {x.titel[:60]} · {x.id}" for x in rows[:25]))
    elif name == "plan":
        a = svc.holen(session, args[0]) if args else None
        if a is None:
            await senden(token, chat_id, "Auftrag nicht gefunden – /plan <id>")
        else:
            t = a.ergebnis or "(kein Text)"
            for i in range(0, min(len(t), 4 * MAX_TEXT), MAX_TEXT):
                await senden(token, chat_id, t[i : i + MAX_TEXT])
    elif name == "stop":
        a = svc.holen(session, args[0]) if args else None
        if a is None or a.status != "laeuft":
            await senden(token, chat_id, "Kein laufender Auftrag mit dieser ID – /stop <id>")
        else:
            await asyncio.to_thread(svc.stoppen, session, a)
            crud_audit.write(session, action="auftrag.stop", target=a.id, actor=f"telegram:{user}")
            await senden(token, chat_id, f"{a.id} gestoppt")
    elif name in ("pause", "weiter"):
        wc.write_setting(session, "runner_angehalten", name == "pause")
        crud_audit.write(session, action="auftrag.runner", actor=f"telegram:{user}", after={"angehalten": name == "pause"})
        await senden(token, chat_id, "Runner angehalten – geplante Aufträge starten nicht, laufende laufen weiter." if name == "pause" else "Runner läuft wieder.")
    elif name in ("neu", "vorschlaege"):
        proj = _projekt_finden(session, cfg, args[0] if args else "")
        if proj is None:
            await senden(token, chat_id, f"Projekt »{args[0] if args else ''}« nicht gefunden (nur Projekte auf {', '.join(cfg.agent_hosts)}). /neu <projekt> <auftragstext>")
            return
        from . import auftrag_vorlagen

        if name == "neu":
            if len(args) < 2 or len(args[1]) < 10:
                await senden(token, chat_id, "Bitte Auftragstext angeben: /neu <projekt> <text>")
                return
            a = svc.anlegen(session, titel=args[1][:80], text=args[1], host=proj["host"], projekt=proj["pfad"], projekt_name=proj["name"],
                            agent="claude", modus="plan_freigabe", profil="bearbeiten_tests", prioritaet=3, zeitfenster="sofort", status="geplant")
            antwort = f"Auftrag {a.id} für {proj['name']} eingeplant (Claude, Plan mit Freigabe)."
        else:
            v = next((x for x in auftrag_vorlagen.vorlagen(cfg.auftrag_vorlagen) if x["id"] == "vorschlaege"), None)
            if v is None:
                await senden(token, chat_id, "Vorlage »vorschlaege« fehlt")
                return
            a = svc.anlegen(session, titel=v["titel"].replace("{projekt}", proj["name"]), text=v["text"], host=proj["host"], projekt=proj["pfad"], projekt_name=proj["name"],
                            agent="codex", modus="bericht", profil="lesen", prioritaet=2, zeitfenster="sofort", status="geplant")
            antwort = f"Vorschlagslauf {a.id} für {proj['name']} eingeplant (Codex)."
        crud_audit.write(session, action=f"auftrag.{name}", target=a.id, actor=f"telegram:{user}", after={"projekt": proj["pfad"]})
        await senden(token, chat_id, antwort)
    else:
        await senden(token, chat_id, f"Unbekanntes Kommando /{name}. /hilfe zeigt alle.")


def _projekt_finden(session: Session, cfg: wc.WallConfig, name: str) -> dict | None:
    """Projekt auf einem Agenten-Host nach Kurzname (Werkstatt → work_dirs → flow-agent)."""
    if not name:
        return None
    from ..routes.overview import _secret_value
    from . import flow_agent as fa
    from . import wall_loop

    n = name.lower()
    stand = wall_loop.letzter_stand() or {}
    for w in stand.get("werkstatt") or []:
        basis = cfg.work_dirs.get(w.get("host") or "")
        if not basis or w.get("host") not in cfg.agent_hosts:
            continue
        for r in w.get("repos") or []:
            if str(r.get("name", "")).lower() == n:
                return {"host": w["host"], "pfad": f"{basis.rstrip('/')}/{r.get('name')}", "name": str(r.get("name"))}
    for host, basis in cfg.work_dirs.items():
        if host in cfg.agent_hosts and basis.rstrip("/").rsplit("/", 1)[-1].lower() == n:
            return {"host": host, "pfad": basis, "name": n}
    f = cfg.flow_agent or {}
    token = _secret_value(session, str(f.get("secret_key") or "flow_agent_read_key"))
    if token:
        for p in fa.projekte(str(f.get("url") or "https://agent.flowaudit.de"), token, f.get("hosts") if isinstance(f.get("hosts"), dict) else {}):
            if p["host"] in cfg.agent_hosts and p["name"].lower() == n:
                return {"host": p["host"], "pfad": p["pfad"], "name": p["name"]}
    return None


async def update_verarbeiten(session: Session, cfg: wc.WallConfig, update: dict, token: str, chat_id: str, dialog: dict) -> None:
    cq = update.get("callback_query")
    if isinstance(cq, dict):
        msg = cq.get("message") or {}
        if not _erlaubt(cq.get("from"), msg.get("chat"), chat_id, dialog):
            crud_audit.write(session, action="telegram.abgewiesen", after={"from": (cq.get("from") or {}).get("id"), "chat": (msg.get("chat") or {}).get("id")})
            await _api(token, "answerCallbackQuery", callback_query_id=cq.get("id"), text="Nicht erlaubt")
            return
        geprueft = callback_pruefen(str(cq.get("data") or ""), _key(session))
        if not geprueft:
            await _api(token, "answerCallbackQuery", callback_query_id=cq.get("id"), text="Schaltfläche abgelaufen oder ungültig")
            return
        aktion, auftrag_id = geprueft
        a = svc.holen(session, auftrag_id)
        user = str((cq.get("from") or {}).get("id") or "?")
        if a is None:
            antwort = "Auftrag existiert nicht mehr"
        else:
            antwort = await _aktion(session, cfg, aktion, a, token, chat_id, user)
        await _api(token, "answerCallbackQuery", callback_query_id=cq.get("id"), text=antwort[:190])
        if aktion not in ("hinweis", "antworten", "plan") and msg.get("message_id"):
            await _tastatur_entfernen(token, chat_id, int(msg["message_id"]))
            await senden(token, chat_id, f"→ {antwort}")
        return
    msg = update.get("message")
    if isinstance(msg, dict):
        if not _erlaubt(msg.get("from"), msg.get("chat"), chat_id, dialog):
            crud_audit.write(session, action="telegram.abgewiesen", after={"from": (msg.get("from") or {}).get("id"), "chat": (msg.get("chat") or {}).get("id")})
            return
        await _text_verarbeiten(session, cfg, msg, token, chat_id, str((msg.get("from") or {}).get("id") or "?"))


async def dialog_loop(stop_event: asyncio.Event, *, pause_s: int = 3) -> None:
    """Long-Polling der Bot-Updates – nur wenn Push und Dialog aktiv sind (Leitinstanz)."""
    log.info("Telegram-Dialog startet.")
    factory = get_session_factory()
    while not stop_event.is_set():
        session = factory()
        try:
            cfg = wc.load(session)
            pcfg = cfg.push or {}
            token, chat_id, dialog = _zugang(session, cfg)
            if not pcfg.get("aktiv") or not dialog.get("aktiv", True) or not token or not chat_id:
                session.close()
                try:
                    await asyncio.wait_for(stop_event.wait(), timeout=30)
                except TimeoutError:
                    pass
                continue
            offset = int(wc.read_setting(session, "telegram_offset", 0) or 0)
            updates = await _api(token, "getUpdates", offset=offset, timeout=25, allowed_updates=["message", "callback_query"])
            for u in updates if isinstance(updates, list) else []:
                uid = int(u.get("update_id", 0))
                try:
                    await update_verarbeiten(session, cfg, u, token, chat_id, dialog)
                except Exception as exc:  # noqa: BLE001 - ein kaputtes Update darf den Dialog nicht stoppen
                    log.warning("Telegram-Update %s: %s", uid, exc)
                wc.write_setting(session, "telegram_offset", uid + 1)
        except Exception as exc:  # noqa: BLE001
            log.warning("Telegram-Dialog: %s", exc)
        finally:
            session.close()
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=pause_s)
        except TimeoutError:
            continue
    log.info("Telegram-Dialog stoppt.")
