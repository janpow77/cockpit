from types import SimpleNamespace

from cockpit.routes.overview import build_projects
from cockpit.services import flow_agent, push
from cockpit.services.wall_config import WallConfig


def test_quota_updates_and_legacy_state_do_not_send_recovery():
    old = ["warn|Claude: Limit 7 Tage zu 87 % ausgeschöpft"]
    new = [{"level": "warn", "text": "Claude: Limit 7 Tage zu 91 % ausgeschöpft"}]
    added, resolved, state, counters = push.bestaetigen(old, {}, new, laeufe=1)
    assert not added and not resolved and not counters
    assert state == [push.schluessel(new[0])]
    assert push.bestaetigen(state, {}, [], laeufe=1)[1] == state


def test_codex_quota_updates_and_severity_change():
    old = [{"level": "warn", "text": "Codex/ChatGPT: Limit 7 Tage zu 86 % ausgeschöpft"}]
    new = [{"level": "warn", "text": "Codex/ChatGPT: Limit 7 Tage zu 95 % ausgeschöpft"}]
    state = [push.schluessel(old[0])]
    assert push.bestaetigen(state, {}, new, laeufe=1)[:2] == ([], [])
    new[0]["level"] = "krit"
    added, removed, _, _ = push.bestaetigen(state, {}, new, laeufe=1)
    assert added == new
    assert push.echte_entwarnungen(removed, new) == []


def test_duplicate_offline_warning_migrates_without_false_recovery():
    old = ["krit|flow-agent: Host janpow-ai offline", "krit|Host janpow-ai ist offline"]
    current = [{"level": "krit", "text": "Host janpow-ai ist offline"}]
    added, removed, state, _ = push.bestaetigen(old, {}, current, laeufe=1)
    assert not added and not removed and len(state) == 1


def test_numeric_changes_keep_identity_but_hosts_remain_separate():
    assert push.schluessel({"level": "warn", "text": "Platte auf nuc zu 81 % voll"}) == push.schluessel({"level": "warn", "text": "Platte auf nuc zu 89 % voll"})
    assert push.schluessel({"level": "warn", "text": "Platte auf nuc1 zu 81 % voll"}) != push.schluessel({"level": "warn", "text": "Platte auf nuc2 zu 81 % voll"})


def test_offline_agent_is_not_an_offline_host_or_stale_sync_alarm():
    data = {"ok": True, "hosts": [{"host": "ccx23", "status": "offline"}],
            "frische": {"befunde": [{"host": "ccx23", "status": "unhealthy", "label": "RAG-Sync"}]}}
    alerts = flow_agent.alarme(data, [{"name": "ccx23", "status": "online"}])
    assert len(alerts) == 1 and "Agentendaten" in alerts[0]["text"]
    assert "offline" not in alerts[0]["text"]
    assert flow_agent.alarme(data, [{"name": "ccx23", "status": "offline"}]) == []


def test_successful_jobs_and_configured_stops_only():
    host = SimpleNamespace(id="nuc", name="nuc")
    rows = [
        {"name": "backend", "service": "backend", "state": "running"},
        {"name": "init", "service": "storage-init", "state": "exited", "exit_code": 0},
        {"name": "dev", "service": "frontend-dev", "state": "exited", "exit_code": 0},
    ]
    project = {"name": "app", "containers": 3, "running": 1, "status": "degraded", "names": ["backend", "init", "dev"], "container_rows": rows}
    cfg = WallConfig(inactive_services={"nuc/app": ["frontend-dev"]})
    result = build_projects(host, [project], [], cfg, {})[0]
    assert result["status"] == "healthy" and result["containers"] == 1
    assert result["ignored_stopped"] == ["init", "dev"]
    rows[1]["exit_code"] = 1
    assert build_projects(host, [project], [], cfg, {})[0]["status"] == "degraded"
    rows[1]["exit_code"] = 0
    rows[0].update(state="exited", exit_code=0)
    assert build_projects(host, [project], [], cfg, {})[0]["status"] == "down"
    assert build_projects(host, [project], [], WallConfig(), {})[0]["containers"] == 2
