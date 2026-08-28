"""Telegram-Dialog: signierte Schaltflächen, Kommandos, Nachrichtentexte, Kurzfassung-Fallback (rein)."""

from types import SimpleNamespace

from cockpit.services import kurzfassung
from cockpit.services import telegram_dialog as td


def test_callback_signatur_und_ablauf():
    d = td.callback_data("freigeben", "a_1", "geheim", jetzt=1000)
    assert d.startswith("freigeben:a_1:") and len(d.encode()) <= 64
    assert td.callback_pruefen(d, "geheim", jetzt=2000) == ("freigeben", "a_1")
    assert td.callback_pruefen(d, "anders", jetzt=2000) is None
    assert td.callback_pruefen(d, "geheim", jetzt=1000 + td.ABLAUF_S + 1) is None
    assert td.callback_pruefen(d.replace("a_1", "a_2"), "geheim", jetzt=2000) is None
    assert td.callback_pruefen("kaputt", "geheim") is None


def test_tastaturen():
    k = td.tastatur("freigabe", "a_1", "k")
    labels = [b["text"] for zeile in k["inline_keyboard"] for b in zeile]
    assert "✅ Freigeben" in labels and "📄 Ganzer Plan" in labels
    assert all(td.callback_pruefen(b["callback_data"], "k") for zeile in k["inline_keyboard"] for b in zeile)
    assert td.tastatur("laeuft", "a_1", "k") is None
    fertig_pr = td.tastatur("fertig", "a_1", "k", pr_vorhanden=True)
    assert [b["text"] for z in fertig_pr["inline_keyboard"] for b in z] == ["🧹 Worktree aufräumen"]


def test_kommandos():
    assert td.kommando_parsen("/status") == ("status", [])
    assert td.kommando_parsen("/neu cockpit Mach die README schöner") == ("neu", ["cockpit", "Mach die README schöner"])
    assert td.kommando_parsen("/vorschläge regulierung") == ("vorschlaege", ["regulierung", ""])
    assert td.kommando_parsen("/stop@cockpitbot a_1") == ("stop", ["a_1"])
    assert td.kommando_parsen("hallo") is None


def test_nachrichtentext_und_pruefung():
    a = SimpleNamespace(id="a_1", titel="README ergänzen", projekt_name="cockpit", agent="claude", status="freigabe", fehler=None, dauer_s=None,
                        kosten_usd=None, diff_url=None, pruefung=None, pruefung_ok=None)
    t = td.nachrichtentext(a, "Drei Sätze Plan.", "http://x/admin/kanban")
    assert t.startswith("📋 Plan liegt vor") and "Drei Sätze Plan." in t and t.endswith("http://x/admin/kanban")
    a2 = SimpleNamespace(**{**a.__dict__, "status": "fertig", "dauer_s": 129, "kosten_usd": 1.1, "diff_url": "https://d",
                            "pruefung": '[{"befehl": "pytest -q", "ok": true}, {"befehl": "ruff", "ok": false}]', "pruefung_ok": False})
    assert td.pruefung_kurz(a2) == "Prüfung ❌ rot: ruff"
    t2 = td.nachrichtentext(a2, "", None, td.pruefung_kurz(a2))
    assert "Dauer 2 min 9 s · 1.10 $" in t2 and "https://d" in t2


def test_kurzfassung_fallback():
    assert kurzfassung.fallback("a  b\n c", 10) == "a b c"
    lang = "x" * 500
    assert kurzfassung.fallback(lang, 100).endswith("…") and len(kurzfassung.fallback(lang, 100)) == 100
