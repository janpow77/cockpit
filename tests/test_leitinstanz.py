from cockpit.services import leitinstanz as li


def test_betrifft_und_ziel_url():
    assert li.betrifft("/admin/api/auftraege") and li.betrifft("/admin/api/auftraege/a_1/start")
    assert not li.betrifft("/admin/api/auftraegex") and not li.betrifft("/admin/api/overview")
    assert li.ziel_url("http://100.99.159.80:7843/", "/admin/api/auftraege", "x=1") == "http://100.99.159.80:7843/admin/api/auftraege?x=1"
    assert li.url_aus({"url": " "}) is None and li.url_aus({"url": "http://h:7843"}) == "http://h:7843"
