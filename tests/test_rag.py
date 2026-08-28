"""Reine Bausteine des Kira-RAG der KI-Konsole: Normalisierung und Kontextblock."""

from cockpit.services import rag


def test_memory_quellen_filtert_und_kuerzt():
    results = [
        {"id": "1", "category": "session_log", "project": "regulierung", "content": "commit …", "score": 0.9},
        {"id": "2", "category": "architecture", "project": "regulierung", "content": "FEATURE: Demo-Modus\nDetails " + "x" * 2000, "score": 0.5352, "created_at": "2026-08-27T13:26:25"},
        {"id": "3", "category": "solution", "project": "x_chat", "content": "privat", "score": 0.4},
        {"id": "4", "category": "reference", "project": None, "summary": "Kurz", "content": "lang", "score": None},
    ]
    q = rag.memory_quellen(results, limit=5, hide=["x_chat"])
    assert [x["id"] for x in q] == ["2", "4"]
    assert q[0]["titel"] == "FEATURE: Demo-Modus" and len(q[0]["text"]) <= rag.MAX_TEXT_MEMORY and q[0]["score"] == 0.535
    assert q[1]["text"] == "Kurz" and q[1]["project"] is None and q[1]["score"] is None


def test_knowledge_quellen_mit_fundstelle():
    results = [{"chunk_id": "c1", "titel": "Verordnung (EU) 2021/1060", "auszug": "Artikel 74 …", "artikel": "Art. 74", "dokumenttyp": "verordnung", "funding_period": "2021-2027", "score": 0.6276}]
    q = rag.knowledge_quellen(results, limit=3)
    assert q[0]["quelle"] == "knowledge" and q[0]["ref"] == "Art. 74 · verordnung · 2021-2027" and q[0]["id"] == "c1"


def test_kontext_block_nummeriert_quellen():
    quellen = [
        {"quelle": "memory", "titel": "t", "text": "Demo per ASGITransport", "category": "architecture", "project": "regulierung", "created_at": "2026-08-27T13:26:25", "score": 0.5, "id": "1", "ref": None},
        {"quelle": "knowledge", "titel": "VO 2021/1060", "text": "Artikel 74 …", "category": "verordnung", "project": None, "created_at": None, "score": 0.6, "id": "c1", "ref": "Art. 74"},
    ]
    block = rag.kontext_block(quellen)
    assert "[1] Gedächtnis · architecture · regulierung · 27.08.2026: Demo per ASGITransport" in block
    assert "[2] Wissensbasis · VO 2021/1060 · Art. 74: Artikel 74 …" in block
    assert rag.kontext_block([]) == ""


def test_json_aus_toolresult_verschachtelt():
    res = {"content": [{"type": "text", "text": "{\"result\": \"{\\\"results\\\": [{\\\"id\\\": \\\"1\\\"}]}\"}"}]}
    assert rag._json_aus_toolresult(res) == {"results": [{"id": "1"}]}
    assert rag._json_aus_toolresult({"content": [{"type": "text", "text": "kein json"}]}) is None


def test_schwellen_und_dubletten():
    mem = [
        {"id": "a", "category": "reference", "content": "Treffer", "score": 0.7},
        {"id": "a", "category": "reference", "content": "Treffer", "score": 0.7},
        {"id": "b", "category": "solution", "content": "Rauschen", "score": 0.21},
    ]
    q = rag.memory_quellen(mem, limit=6, hide=[])
    assert [x["id"] for x in q] == ["a"]
    know = [
        {"chunk_id": "c1", "titel": "Drucksache", "auszug": "Art. 14 …", "score": 0.58},
        {"chunk_id": "c2", "titel": "VO 2021/1060", "auszug": "Artikel 74 …", "score": 0.71},
        {"chunk_id": "c2", "titel": "VO 2021/1060", "auszug": "Artikel 74 …", "score": 0.71},
    ]
    assert [x["id"] for x in rag.knowledge_quellen(know, limit=4)] == ["c2"]
    assert len(rag.knowledge_quellen(know, limit=4, min_score=rag.MIN_SCORE_KNOWLEDGE_ONLY)) == 2
