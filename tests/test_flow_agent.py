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


TOPO = {"nodes": [
    {"id": "host:nuc", "kind": "host", "label": "janpow-NUC15JNLU7X4", "status": "healthy",
     "metrics": {"cpu_percent": 3.0, "memory_used_bytes": 28942438400, "memory_total_bytes": 66687823872,
                 "uptime_seconds": 1121072, "cpu_temperature_celsius": 62.0},
     "metadata": {"role": "gpu-server", "agent_version": "0.2.0", "last_seen_at": "2026-08-29T05:22:05Z"}},
    {"id": "host:evo", "kind": "host", "label": "evo2", "status": "offline", "metrics": {}, "metadata": {}},
    {"id": "c1", "kind": "container", "host_id": "host:nuc", "status": "healthy", "label": "cockpit"},
    {"id": "c2", "kind": "container", "host_id": "host:nuc", "status": "unknown", "label": "bewusst aus"},
    {"id": "g1", "kind": "gpu", "host_id": "host:nuc", "label": "RTX 5060",
     "metrics": {"memory_total_bytes": 8589934592, "memory_used_bytes": 1073741824, "utilization_percent": 12.0, "temperature_celsius": 55.0}},
    {"id": "b1", "kind": "backup", "host_id": "host:nuc", "label": "local", "status": "healthy",
     "metrics": {"size_bytes": 123}, "metadata": {"type": "local", "last_success_at": "2026-08-29T01:00:00Z"}},
]}
OPS = [{"hostname": "janpow-NUC15JNLU7X4",
        "tmux": {"sessions": [{"name": "claude", "windows": 2, "attached": True, "created_at": "2026-08-16T06:33:08Z"}]},
        "tools": [{"name": "restic", "installed": False}, {"name": "git", "installed": True}]}]


def test_hosts_aus_topologie_und_operations():
    h = fa.hosts_aus(TOPO, OPS, {"janpow-NUC15JNLU7X4": "nuc", "evo2": "evo"})
    nuc = h["nuc"]
    assert nuc["ok"] and nuc["quelle"] == "flow-agent" and nuc["cpu_pct"] == 3.0
    assert nuc["mem_total_mb"] == 63598 and nuc["mem_pct"] == 43.4 and nuc["uptime_s"] == 1121072
    assert nuc["containers"] == 1  # nur laufende zählen, bewusst gestoppte nicht
    assert nuc["gpus"][0]["mem_total_mb"] == 8192 and nuc["gpus"][0]["util_pct"] == 12.0
    assert nuc["tmux"][0]["name"] == "claude" and len(nuc["tmux"][0]["windows"]) == 2
    assert nuc["werkzeuge_fehlen"] == ["restic"] and nuc["rolle"] == "gpu-server"
    assert h["evo"]["ok"] is False  # offline
    assert fa.hosts_aus(None, None, {}) == {}


def test_backups_aus_topologie():
    b = fa.backups_aus(TOPO, {"janpow-NUC15JNLU7X4": "nuc"})
    assert b == [{"host": "nuc", "ziel": "local", "status": "healthy", "letzte": "2026-08-29T01:00:00Z",
                  "groesse_b": 123, "art": "local"}]
    assert fa.backups_aus({}, {}) == []


TOPO_LATENZ = {"nodes": [
    {"id": "host:hetzner", "kind": "host", "label": "cockpit-nbg1-1", "status": "healthy",
     "metrics": {}, "metadata": {"role": "gateway"}},
    {"id": "host:nuc", "kind": "host", "label": "janpow-NUC15JNLU7X4", "status": "healthy",
     "metrics": {}, "metadata": {"role": "gpu-server"}},
    {"id": "host:janpow-ai", "kind": "host", "label": "janpow-ai", "status": "healthy",
     "metrics": {}, "metadata": {"role": "gpu-server"}},
    # Weg zur Zentrale – das ist der Wert, den die Kachel zeigt
    {"id": "vpn-peer:nuc:nodekey:aa", "kind": "vpn-peer", "label": "cockpit-nbg1-1",
     "metrics": {"latency_ms": 31.0, "packet_loss_percent": 0.0}},
    {"id": "vpn-peer:janpow-ai:nodekey:bb", "kind": "vpn-peer", "label": "cockpit-nbg1-1",
     "metrics": {"latency_ms": None, "packet_loss_percent": 100.0}},
    # Weg zu einem anderen Knoten – darf die Kachel nicht überschreiben
    {"id": "vpn-peer:nuc:nodekey:cc", "kind": "vpn-peer", "label": "evo2",
     "metrics": {"latency_ms": 8.0, "packet_loss_percent": 0.0}},
]}


def test_latenz_zur_leitinstanz_je_host():
    """Aus den Peer-Messungen wird je Host genau der Weg zur Zentrale übernommen."""
    h = fa.hosts_aus(TOPO_LATENZ, None, {"janpow-NUC15JNLU7X4": "nuc", "janpow-ai": "janpow-ai",
                                         "cockpit-nbg1-1": "hetzner"})
    assert h["nuc"]["latenz_ms"] == 31.0
    assert h["nuc"]["verlust_pct"] == 0.0
    # online gemeldet, antwortet aber nicht
    assert h["janpow-ai"]["latenz_ms"] is None
    assert h["janpow-ai"]["verlust_pct"] == 100.0
    # die Zentrale misst sich nicht selbst
    assert h["hetzner"]["latenz_ms"] is None
    assert h["hetzner"]["verlust_pct"] is None


def test_ohne_gateway_bleibt_die_latenz_leer():
    """Ohne erkennbare Zentrale wird nichts geraten."""
    ohne = {"nodes": [n for n in TOPO_LATENZ["nodes"]
                      if n.get("id") != "host:hetzner"]}
    h = fa.hosts_aus(ohne, None, {"janpow-NUC15JNLU7X4": "nuc"})
    assert h["nuc"]["latenz_ms"] is None
