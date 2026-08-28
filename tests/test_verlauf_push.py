"""Verlauf, Push-Vergleich, tmux-Parser, Werkstatt-Aktivitaet, RAG-Modus, Login-Sperre."""

from datetime import datetime

from cockpit.routes.auth import _fehler, login_erlaubt, login_fehlgeschlagen
from cockpit.routes.chat import rag_modus_effektiv
from cockpit.services import push, verlauf
from cockpit.services import wall_extras as wx
from cockpit.services.host_stats import _parse


def test_werte_aus_stand_und_slug():
    stand = {
        "hosts": [{"name": "nuc", "stats": {"load1": 1.5, "mem_pct": 40.2, "disk_pct": 57, "gpus": [{"util_pct": 30}, {"util_pct": 50}], "containers": 24}}],
        "hero": {"kpis": [{"label": "Meldungen 24 h", "value": 34445}, {"label": "Verdachtsfälle 24 h", "value": 238}]},
        "alerts": [{"level": "krit"}, {"level": "warn"}, {"level": "warn"}],
        "dienste": [{"host": "hpp.flowaudit.de", "ms": 150, "ok": True}],
        "kira": {"total": 6060},
    }
    w = verlauf.werte_aus_stand(stand)
    assert w["host.nuc.load1"] == 1.5 and w["host.nuc.gpu_pct"] == 40.0 and w["host.nuc.containers"] == 24
    assert w["hero.meldungen_24_h"] == 34445 and w["hero.verdachtsfaelle_24_h"] == 238
    assert w["alerts.krit"] == 1 and w["alerts.warn"] == 2
    assert w["dienst.hpp.flowaudit.de.ms"] == 150 and w["kira.total"] == 6060
    assert verlauf.slug("Verfahren offen") == "verfahren_offen"


def test_push_vergleich_und_nachricht():
    alt = ["warn|Sicherung hpp ist 40 h alt", "krit|Host nuc ist offline"]
    neu = [
        {"level": "krit", "text": "Host nuc ist offline"},
        {"level": "warn", "text": "Zertifikat hpp.flowaudit.de läuft in 10 Tagen ab", "hint": None},
        {"level": "info", "text": "Pause offen in cockpit (nuc)"},
    ]
    hinzu, weg = push.vergleich(alt, neu, min_level="warn")
    assert [a["text"] for a in hinzu] == ["Zertifikat hpp.flowaudit.de läuft in 10 Tagen ab"]
    assert weg == ["warn|Sicherung hpp ist 40 h alt"]
    text = push.nachricht(hinzu, weg, "ccx23")
    assert text.startswith("Cockpit ccx23") and "🟠 Zertifikat" in text and "✅ entwarnt: Sicherung hpp" in text


def test_ruhezeit_ueber_mitternacht():
    assert push.in_ruhezeit(datetime(2026, 8, 28, 23, 30), "22:00", "07:00")
    assert push.in_ruhezeit(datetime(2026, 8, 28, 6, 59), "22:00", "07:00")
    assert not push.in_ruhezeit(datetime(2026, 8, 28, 12, 0), "22:00", "07:00")
    assert not push.in_ruhezeit(datetime(2026, 8, 28, 12, 0), None, None)


def test_parse_tmux_und_gpu():
    out = _parse(
        "load 1 1 1\ncpus 8\ngpu 100 164 2048\n"
        "tmuxw\tclaude\tbash\t1\tnode\t1\t1755325988\n"
        "tmuxw\tprojekte\taudit-main\t0\tbash\t0\t1755325988\n"
        "tmuxw\tprojekte\tflowinvoice\t1\tnode\t0\t1755325988\n"
    )
    assert out["gpus"] == [{"util_pct": 100, "mem_used_mb": 164, "mem_total_mb": 2048}]
    namen = {s["name"]: s for s in out["tmux"]}
    assert namen["claude"]["attached"] is True and len(namen["projekte"]["windows"]) == 2
    assert namen["projekte"]["windows"][1] == {"name": "flowinvoice", "active": True, "cmd": "node"}


def test_werkstatt_aktiv_kennzeichen():
    now = 1_700_000_000
    stdout = "\n".join([
        "\t".join(["frisch", "main", "0", str(now - 3600), "0", "0", "x", ""]),
        "\t".join(["alt", "main", "2", str(now - 40 * 86400), "0", "0", "y", ""]),
        "\t".join(["pause", "main", "0", str(now - 40 * 86400), str(now - 86400), "0", "z", "weiter"]),
    ])
    rows = {r["name"]: r for r in wx.parse_werkstatt(stdout, [], now=now, aktiv_tage=14)}
    assert rows["frisch"]["aktiv"] and not rows["alt"]["aktiv"] and rows["pause"]["aktiv"]


def test_rag_modus_wissensbasis_nur_fachlich():
    assert rag_modus_effektiv("both", "Welche Projekte laufen auf dem Hetzner?") == "memory"
    assert rag_modus_effektiv("both", "Was sagt Art. 74 CPR zur Verwaltungskontrolle?") == "both"
    assert rag_modus_effektiv("knowledge", "irgendwas") == "knowledge"


def test_login_sperre_nach_fuenf_fehlversuchen():
    _fehler.clear()
    for i in range(5):
        assert login_erlaubt("10.0.0.1", jetzt=1000 + i)[0]
        login_fehlgeschlagen("10.0.0.1", jetzt=1000 + i)
    erlaubt, rest = login_erlaubt("10.0.0.1", jetzt=1005)
    assert not erlaubt and 0 < rest <= 61
    assert login_erlaubt("10.0.0.1", jetzt=1000 + 61)[0]
    assert login_erlaubt("10.0.0.2", jetzt=1005)[0]
