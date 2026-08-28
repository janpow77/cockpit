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


def test_zustand_und_alarme():
    health = {"status": "ok", "version": "0.2.0"}
    agents = [{"hostname": "janpow-NUC15JNLU7X4", "status": "degraded", "age_seconds": 8, "project_count": 70, "container_count": 53, "gpu_count": 1},
              {"hostname": "evo2", "status": "offline", "age_seconds": 900, "project_count": 1}]
    fresh = {"status": "degraded", "healthy_count": 20, "degraded_count": 1, "unhealthy_count": 1, "findings": [
        {"hostname": "janpow-NUC15JNLU7X4", "check": {"id": "kb-harvest", "label": "Wissensbasis-Harvest", "status": "unknown", "detail": "HTTP 401"}},
        {"hostname": "evo2", "check": {"id": "repl", "label": "RAG-Sync EVO", "status": "unhealthy", "detail": "Replay-Rückstand 2 h"}},
        {"hostname": "evo2", "check": {"id": "ok", "label": "Platte", "status": "healthy", "detail": "ok"}},
    ]}
    meld = {"hosts_offline": ["evo2"], "hosts_degraded": ["janpow-NUC15JNLU7X4"], "pending_actions": 2, "failed_actions_recent": 1}
    ops = [{"hostname": "janpow-NUC15JNLU7X4", "tmux": {"status": "degraded"}, "tools": [{"name": "restic", "installed": False}, {"name": "gh", "installed": True}]}]
    z = fa.zustand_aus("https://agent.flowaudit.de", health, agents, fresh, meld, ops, {"janpow-NUC15JNLU7X4": "nuc", "evo2": "evo"})
    assert z["ok"] and z["version"] == "0.2.0"
    assert [h["host"] for h in z["hosts"]] == ["evo", "nuc"]  # offline zuerst
    nuc = z["hosts"][1]
    assert nuc["werkzeuge_fehlen"] == ["restic"] and nuc["tmux"] == "degraded" and nuc["projekte"] == 70
    assert z["frische"]["unhealthy"] == 1 and [b["status"] for b in z["frische"]["befunde"]] == ["unhealthy", "unknown"]
    assert z["meldungen"]["hosts_offline"] == ["evo"] and z["meldungen"]["pending_actions"] == 2
    al = fa.alarme(z)
    levels = [(a["level"], a["text"]) for a in al]
    assert ("krit", "flow-agent: Host evo offline") in levels
    assert any(lv == "warn" and "RAG-Sync EVO" in tx for lv, tx in levels)
    assert any("fehlgeschlagen" in tx for _, tx in levels) and any("Freigabe" in tx for _, tx in levels)
    weg = fa.zustand_aus("u", None, None, None, None, None, {})
    assert not weg["ok"] and fa.alarme(weg)[0]["level"] == "warn"
