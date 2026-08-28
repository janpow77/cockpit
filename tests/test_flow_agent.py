"""flow-agent als Datenquelle: Antworten in Zeilen, Host-Zuordnung, Kontextblock (rein)."""

from cockpit.services import flow_agent as fa

ANTWORT = [
    {"agent_id": "nuc-1", "hostname": "nuc", "collected_at": "2026-08-28T08:00:00Z", "projects": [
        {"id": "p1", "name": "cockpit", "path": "/home/janpow/Projekte/cockpit/", "root": "/home/janpow/Projekte", "is_git": True, "status": "healthy", "branch": "master", "dirty": True, "ahead": 2, "technologies": ["python", "vue"]},
        {"id": "p2", "name": "notizen", "path": "/home/janpow/Projekte/notizen", "is_git": False},
    ]},
    {"agent_id": "evo-1", "hostname": "evo.local", "collected_at": "2026-08-27T08:00:00Z", "projects": [
        {"id": "p3", "name": "flow-agent", "path": "/srv/flow-agent", "is_git": True, "status": "degraded", "branch": "main"},
    ]},
]


def test_projekte_aus_antwort():
    rows = fa.projekte_aus(ANTWORT, {"evo.local": "evo-desktop"})
    assert [(r["host"], r["name"]) for r in rows] == [("nuc", "cockpit"), ("nuc", "notizen"), ("evo-desktop", "flow-agent")]
    c = rows[0]
    assert c["pfad"] == "/home/janpow/Projekte/cockpit" and c["dirty"] and c["ahead"] == 2 and "vue" in c["technologien"]
    assert rows[1]["git"] is False
    assert fa.projekte_aus(None, {}) == [] and fa.projekte_aus({"detail": "x"}, {}) == []


def test_graphify_aus_antwort():
    g = fa.graphify_aus([{"hostname": "nuc", "graphify": {"generated_at": "2026-08-27T01:00:00Z", "projects": [{"name": "cockpit", "node_count": 120, "edge_count": 300, "status": "healthy"}]}}], {})
    assert g[("nuc", "cockpit")]["knoten"] == 120 and g[("nuc", "cockpit")]["generiert"].startswith("2026-08-27")


def test_projekt_kontext():
    p = fa.projekte_aus(ANTWORT, {})[0]
    g = {"generiert": "2026-08-27T01:00:00Z", "knoten": 120, "kanten": 300, "status": "healthy"}
    text = fa.projekt_kontext(p, g, [{"message": "Backup älter als 3 Tage"}])
    assert "flow-agent" in text and "uncommittete Änderungen" in text and "2 Commit(s) vor dem Remote" in text
    assert "120 Knoten" in text and "Backup älter" in text
    assert fa.projekt_kontext(None, None) == ""
