"""Reine Bausteine der Wand: Ausblendliste, Links, Modell-Whitelist, Host-Kennzahlen."""

from types import SimpleNamespace

from cockpit.routes.chat import allowed_models
from cockpit.routes.overview import _newest_backups, build_projects, intern_urls
from cockpit.services import wall_config as wc
from cockpit.services.host_stats import _parse


def test_is_hidden_teilstring_ohne_gross_klein():
    hide = ["love-ai", "Sarah", "kino"]
    assert wc.is_hidden("love-ai-web", hide)
    assert wc.is_hidden("sarah-qwen36", hide)
    assert not wc.is_hidden("hpp-backend", hide)


def test_link_und_label_ueber_projekt_oder_container_praefix():
    links = {"hpp": "https://hpp.example", "checklist": "https://cl.example"}
    assert wc.link_for("hpp", [], links) == "https://hpp.example"
    assert wc.link_for("regulierung", ["hpp-backend", "hpp-frontend"], links) == "https://hpp.example"
    assert wc.link_for("kino", ["kino-web-1"], links) is None
    lab = wc.label_for("regulierung", ["hpp-backend"], wc.DEFAULT_LABELS)
    assert lab["title"].startswith("HPP")


def test_allowed_models_ist_schnittmenge_mit_router():
    cfg = wc.WallConfig(chat_models=[{"tag": "qwen3.8-heretic:27b", "label": "Qwen 3.8 · 27B"}, {"tag": "nicht-da", "label": "x"}])
    available = [{"name": "qwen3.8-heretic:27b", "parameter_size": "26.9B", "size_bytes": 1}, {"name": "sarah-x", "parameter_size": "36B", "size_bytes": 2}]
    out = allowed_models(cfg, available)
    assert [m["tag"] for m in out] == ["qwen3.8-heretic:27b"]
    assert out[0]["label"] == "Qwen 3.8 · 27B"


def test_build_projects_blendet_aus_und_verknuepft_registrierung():
    host = SimpleNamespace(id="h1", name="ccx23")
    projects = [
        {"name": "regulierung", "containers": 5, "running": 5, "status": "healthy", "names": ["hpp-backend", "hpp-cloudflared"], "images": []},
        {"name": "kino", "containers": 3, "running": 3, "status": "healthy", "names": ["kino-web-1"], "images": []},
    ]
    app = SimpleNamespace(id="a1", host_id="h1", enabled=True, name="hpp", container_filter="name=hpp-", last_status="healthy", last_check_at="2026-08-27T10:00:00Z")
    cfg = wc.WallConfig()
    out = build_projects(host, projects, [app], cfg, {"a1": {"ts": "t", "git_sha": "abc1234", "image": "i", "status": "ok"}})
    assert [p["name"] for p in out] == ["regulierung"]
    p = out[0]
    assert p["registered"] and p["app_id"] == "a1" and p["deploy"]["git_sha"] == "abc1234"
    assert p["url"] == "https://hpp.flowaudit.de" and p["tunnel"] is True
    assert p["title"].startswith("HPP")


def test_host_stats_parse():
    out = _parse("load 0.81 0.62 0.55\nmem 15990 9012\ndisk 154000000 100000000 70%\nuptime 864000\ncpus 4\ncontainers 31\n")
    assert out["load1"] == 0.81 and out["cpus"] == 4 and out["containers"] == 31
    assert out["mem_pct"] == 56.4 and out["disk_pct"] == 70.0 and out["uptime_s"] == 864000
    leer = _parse("")
    assert leer["load1"] is None and leer["containers"] is None


def test_newest_backups(tmp_path):
    (tmp_path / "hpp_backup.log").write_text("log")  # Protokolle sind keine Sicherungen
    (tmp_path / "hpp-20260826-031000.dump.age").write_bytes(b"x" * 10)
    (tmp_path / "hpp-20260827-031000.dump.age").write_bytes(b"x" * 20)
    (tmp_path / "checklist-20260827-032000.dump.age").write_bytes(b"y")
    rows = _newest_backups(str(tmp_path))
    assert [r["name"] for r in rows] == ["checklist", "hpp"]
    hpp = next(r for r in rows if r["name"] == "hpp")
    assert hpp["file"].startswith("hpp-20260827") and hpp["size_bytes"] == 20 and hpp["status"] == "ok"
    assert _newest_backups(str(tmp_path / "gibt-es-nicht")) == []


def test_waehle_hero_bevorzugt_host_dann_tunnel():
    from cockpit.routes.overview import waehle_hero
    projs = [
        {"host": "nuc", "name": "regulierung", "title": "HPP", "tunnel": False},
        {"host": "ccx23", "name": "regulierung", "title": "HPP", "tunnel": True},
    ]
    assert waehle_hero(projs, {"project": "hpp", "host": "ccx23"})["host"] == "ccx23"
    assert waehle_hero(projs, {"project": "hpp"})["host"] == "ccx23"  # Tunnel = Prod
    assert waehle_hero(projs, {"project": "gibt-es-nicht"}) is None


def test_intern_urls_aus_ports():
    rows = [
        {"name": "hpp-frontend", "service": "frontend", "ports": "0.0.0.0:3003->80/tcp, [::]:3003->80/tcp"},
        {"name": "hpp-backend", "service": "backend", "ports": "127.0.0.1:8090->8000/tcp"},
        {"name": "cockpit", "service": "cockpit", "ports": "100.99.159.80:7843->7843/tcp"},
        {"name": "db", "service": "db", "ports": "5432/tcp"},
        {"name": "fremd", "service": "x", "ports": "10.0.0.5:9000->9000/tcp"},
    ]
    out = intern_urls(rows, "100.99.159.80")
    assert [e["url"] for e in out] == ["http://100.99.159.80:3003", "http://100.99.159.80:7843"]
    assert out[0]["service"] == "frontend"
    assert intern_urls(rows, None) == []


def test_login_prueft_benutzername_und_passwort(monkeypatch):
    from fastapi.testclient import TestClient

    from cockpit.main import app

    monkeypatch.setenv("COCKPIT_ADMIN_PASSWORD", "geheim-123")
    with TestClient(app) as c:
        assert c.post("/admin/api/auth/login", json={"password": "geheim-123"}).status_code == 200
        assert c.post("/admin/api/auth/login", json={"username": "admin", "password": "geheim-123"}).status_code == 200
        assert c.post("/admin/api/auth/login", json={"username": "fremd", "password": "geheim-123"}).status_code == 401
        assert c.post("/admin/api/auth/login", json={"username": "admin", "password": "falsch"}).status_code == 401


def test_tmux_sonde_versteht_beide_trennzeichen():
    """tmux 3.6 ersetzt Tabulatoren in Format-Ausgaben durch Unterstriche – daher |~| als Trenner."""
    from cockpit.services import host_stats

    neu = "tmuxw|~|arbeit|~|shell|~|1|~|bash|~|0|~|1787939894|~|0"
    alt = "tmuxw\tclaude\t\t1\tbash\t1\t1786861988\t1"
    assert [s["name"] for s in host_stats._parse(neu)["tmux"]] == ["arbeit"]
    assert [s["name"] for s in host_stats._parse(alt)["tmux"]] == ["claude"]
    beide = host_stats._parse(neu + "\n" + alt)["tmux"]
    assert sorted(s["name"] for s in beide) == ["arbeit", "claude"]
    assert host_stats._parse(neu)["tmux"][0]["windows"][0]["cmd"] == "bash"
    assert "|~|" in host_stats._CMD and "tmuxw\\t" not in host_stats._CMD
