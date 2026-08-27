"""Reine Bausteine der Mehrwert-Kacheln: Werkstatt-Parser, Kira-Parser, Handlungsbedarf."""

from cockpit.services import wall_extras as wx


def test_parse_werkstatt_sortiert_pausen_und_offene_arbeit_zuerst():
    now = 1_700_000_000
    stdout = "\n".join([
        "\t".join(["regulierung", "main", "3", str(now - 3600), "0", "0", "feat: wand", ""]),
        "\t".join(["cockpit", "feat/wand", "0", str(now - 7200), str(now - 600), "2", "wip: stand", "- ChatView bauen"]),
        "\t".join(["x_chat", "main", "9", str(now - 60), "0", "-", "privat", ""]),
        "\t".join(["alt", "main", "0", str(now - 86400 * 40), "0", "-", "", ""]),
        "kaputte zeile",
    ])
    rows = wx.parse_werkstatt(stdout, ["x_chat"], now=now)
    # cockpit: Pause vor 10 min ist die juengste Aktivitaet, dann regulierung (Commit vor 1 h), dann alt
    assert [r["name"] for r in rows] == ["cockpit", "regulierung", "alt"]
    assert rows[0]["pause"] is not None and rows[0]["pause_age_h"] == 0.2 and rows[0]["next_step"] == "ChatView bauen" and rows[0]["ahead"] == 2
    assert rows[1]["dirty"] == 3 and rows[1]["age_h"] == 1.0 and rows[1]["ahead"] == 0
    assert rows[2]["ahead"] is None and rows[2]["message"] == ""
    assert "_aktiv" not in rows[0]


def test_werkstatt_cmd_quotet_pfad_und_liefert_tsv():
    cmd = wx.werkstatt_cmd("/home/deploy/Projekte/")
    assert "/home/deploy/Projekte/*/.git" in cmd
    assert "safe.directory" in cmd and "session_resume.md" in cmd
    assert cmd.count("%s\\t") == 7


def test_parse_kira_filtert_protokolle_und_private_projekte():
    stdout = (
        '{"total_entries": 1284}\n---KIRA---\n['
        '{"id": "1", "category": "session_log", "project": "regulierung", "content": "commit ..."},'
        '{"id": "2", "category": "architecture", "project": "regulierung", "summary": "Demo-Modus per ASGITransport", "tags": ["demo"], "created_at": "2026-08-27T10:00:00"},'
        '{"id": "3", "category": "solution", "project": "x_chat", "content": "geheim"},'
        '{"id": "4", "category": "solution", "project": null, "content": "Trigger-Pause beim Demo-Löschen", "tags": []}'
        "]"
    )
    out = wx.parse_kira(stdout, ["x_chat"], limit=8)
    assert out["ok"] and out["total"] == 1284
    assert [e["id"] for e in out["entries"]] == ["2", "4"]
    assert out["entries"][0]["text"].startswith("Demo-Modus")


def test_parse_kira_mit_fehlerantwort():
    out = wx.parse_kira('{"detail": "Invalid API key"}\n---KIRA---\n{"detail": "Invalid API key"}', [])
    assert out["ok"] is False and out["total"] is None and "Invalid API key" in (out["note"] or "")


def test_kira_cmd_liest_schluessel_auf_dem_host():
    cmd = wx.kira_cmd({"url": "http://127.0.0.1:8003/api/memory", "env_file": "/home/janpow/Projekte/audit_designer/.env"})
    assert "sed -n 's/^MEMORY_API_KEY=//p'" in cmd and "X-Memory-API-Key" in cmd
    assert "/entries?limit=40" in cmd and "---KIRA---" in cmd


def test_handlungsbedarf_leer_wenn_alles_laeuft():
    hosts = [{"name": "ccx23", "is_self": True, "status": "online", "stats": {"ok": True, "disk_pct": 40, "mem_pct": 50, "load1": 0.5, "cpus": 4}}]
    projects = [
        {"host": "ccx23", "name": "hpp", "title": "HPP", "status": "healthy", "running": 5, "containers": 5, "registered": True},
        {"host": "nuc", "name": "krypto", "title": "krypto", "status": "down", "running": 0, "containers": 3, "registered": False, "url": None},
        # Dev-Kopie mit oeffentlicher Adresse auf einem Nicht-Produktionshost: kein Alarm
        {"host": "nuc", "name": "zvg", "title": "ZVG", "status": "down", "running": 0, "containers": 2, "registered": False, "url": "https://zvg.example", "tunnel": False},
    ]
    dienste = [{"host": "hpp.flowaudit.de", "ok": True, "ms": 120, "tls_tage": 60}]
    out = wx.handlungsbedarf(hosts, projects, [{"name": "hpp", "status": "ok", "age_h": 5}], dienste, {"ok": True}, {"enabled": False}, [])
    assert out == []


def test_handlungsbedarf_sortiert_nach_schwere():
    hosts = [
        {"name": "nuc", "is_self": False, "status": "offline", "stats": {}},
        {"name": "ccx23", "is_self": True, "status": "online", "stats": {"ok": True, "disk_pct": 86, "mem_pct": 95, "load1": 9, "cpus": 4}},
    ]
    projects = [{"host": "ccx23", "name": "cl", "title": "Checklist", "status": "degraded", "running": 8, "containers": 9, "url": None, "registered": True}]
    backups = [{"name": "hpp", "status": "krit", "age_h": 80}]
    dienste = [{"host": "zvg.flowaudit.de", "ok": False, "note": "ConnectTimeout", "url": "https://zvg.flowaudit.de"},
               {"host": "hpp.flowaudit.de", "ok": True, "ms": 4000, "tls_tage": 5, "url": "https://hpp.flowaudit.de"}]
    werkstatt = [{"host": "nuc", "ok": True, "repos": [
        {"name": "cockpit", "pause": "2026-08-27T10:00:00Z", "pause_age_h": 3.0, "next_step": "Deploy"},
        {"name": "uralt", "pause": "2026-05-01T10:00:00Z", "pause_age_h": 2800.0, "next_step": "vergessen"},
    ]}]
    out = wx.handlungsbedarf(hosts, projects, backups, dienste, {"ok": False}, {"enabled": True, "error": "rate limit"}, werkstatt)
    levels = [a["level"] for a in out]
    assert levels == sorted(levels, key=lambda l: {"krit": 0, "warn": 1, "info": 2}[l])
    assert levels[0] == "krit" and levels[-1] == "info"
    texte = " | ".join(a["text"] for a in out)
    assert "Host nuc ist offline" in texte and "Zertifikat hpp.flowaudit.de" in texte and "Pause offen in cockpit" in texte
    assert "uralt" not in texte
    assert out[-1]["hint"] == "Deploy"


def test_handlungsbedarf_registrierte_dev_stacks_bleiben_still():
    hosts = [{"name": "ccx23", "is_self": True, "status": "online", "stats": {"ok": True}},
             {"name": "nuc", "is_self": False, "status": "online", "stats": {"ok": True}}]
    projects = [
        {"host": "nuc", "name": "krypto", "title": "krypto", "status": "down", "running": 0, "containers": 3, "registered": True, "url": None, "tunnel": False},
        {"host": "nuc", "name": "hpp", "title": "HPP", "status": "degraded", "running": 4, "containers": 5, "registered": True, "url": "https://hpp.example", "tunnel": True},
    ]
    out = wx.handlungsbedarf(hosts, projects, [], [], {"ok": True}, None, [])
    assert [a["text"] for a in out] == ["HPP auf nuc: 4/5 Container laufen"]


def test_handlungsbedarf_oeffentliche_instanz_auf_prod_host_zaehlt():
    hosts = [{"name": "ccx23", "is_self": True, "status": "online", "stats": {"ok": True}}]
    projects = [{"host": "ccx23", "name": "zvg", "title": "ZVG", "status": "down", "running": 0, "containers": 2, "registered": False, "url": "https://zvg.example", "tunnel": False}]
    out = wx.handlungsbedarf(hosts, projects, [], [], {"ok": True}, None, [])
    assert len(out) == 1 and out[0]["level"] == "krit" and "ZVG auf ccx23" in out[0]["text"]


def test_handlungsbedarf_laptop_aus_ist_nur_hinweis():
    hosts = [{"name": "macbook-air", "description": "Laptop", "is_self": False, "status": "ssh-down", "stats": {}}]
    out = wx.handlungsbedarf(hosts, [], [], [], {"ok": True}, None, [])
    assert out == [{"level": "info", "text": "Laptop macbook-air ist ssh-down", "host": "macbook-air", "hint": None, "url": None}]


def test_parse_kira_bereinigt_text():
    stdout = '{"total_entries": 1}\n---KIRA---\n[{"id": "1", "category": "solution", "project": "p", "content": "PROBLEM: Zeile eins\\nZeile   zwei"}]'
    out = wx.parse_kira(stdout, [])
    assert out["entries"][0]["text"] == "Zeile eins Zeile zwei"
