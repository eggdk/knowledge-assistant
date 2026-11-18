"""Direct knowledge entries must use the same retrieval and version lifecycle."""

import pytest
from fastapi.testclient import TestClient

from app.config import get_database_path
from app.knowledge_store import delete_document
from app.main import app


@pytest.fixture
def client(tmp_path):
    app.dependency_overrides[get_database_path] = lambda: tmp_path / "qa.sqlite3"
    try:
        with TestClient(app) as http:
            yield http
    finally:
        app.dependency_overrides.clear()


def test_qa_pair_create_search_edit_delete_and_isolation(client):
    kb_id = client.post("/api/knowledge-bases", json={"name": "测试"}).json()["id"]
    base = f"/api/knowledge-bases/{kb_id}"
    entry = {"question": " 巡检周期是多久？ ", "answer": " 十九天 "}
    response = client.post(base + "/qa-pairs", json=entry)
    assert response.status_code == 201
    created = response.json()
    assert created["status"] == "created" and created["searchable"]
    document_id = created["document_id"]
    entry_url = base + "/qa-pairs/" + document_id
    detail_url = base + "/documents/" + document_id
    detail = client.get(detail_url).json()
    assert detail["content"] == "问题：\n巡检周期是多久？\n\n回答：\n十九天\n"
    assert client.put(entry_url, json=entry).json()["status"] == "unchanged"
    entry["answer"] = "二十八天"
    changed = client.put(entry_url, json=entry).json()
    assert changed["status"] == "updated" and changed["version_no"] == 2
    hits = client.post(base + "/questions", json={"question": "巡检周期"}).json()["matches"]
    assert "二十八天" in hits[0]["content"] and hits[0]["relative_path"] == created["relative_path"]
    assert "十九天" in client.get(detail_url + "?version_no=1").json()["content"]
    other = client.post("/api/knowledge-bases", json={"name": "别的库"}).json()["id"]
    assert client.put(f"/api/knowledge-bases/{other}/qa-pairs/{document_id}", json=entry).status_code == 404
    assert client.delete(detail_url).status_code == 204
    assert client.put(entry_url, json=entry).status_code == 404
    assert client.post(base + "/questions", json={"question": "巡检周期"}).json()["matches"] == []


def test_qa_pair_rejects_blank_fields_and_editing_uploaded_documents(client):
    kb_id = client.post("/api/knowledge-bases", json={"name": "测试"}).json()["id"]
    base = f"/api/knowledge-bases/{kb_id}"
    for body in ({"question": " ", "answer": "A"}, {"question": "Q", "answer": "\n"}):
        assert client.post(base + "/qa-pairs", json=body).status_code == 422
    client.post(base + "/documents/import", files={"files": ("guide.txt", b"guide")})
    document_id = client.get(base + "/documents").json()[0]["id"]
    assert client.put(base + "/qa-pairs/" + document_id, json={"question": "Q", "answer": "A"}).status_code == 422
    assert client.post("/api/knowledge-bases/missing/qa-pairs", json={"question": "Q", "answer": "A"}).status_code == 404


def test_edit_does_not_restore_entry_deleted_during_request(client, monkeypatch):
    kb_id = client.post("/api/knowledge-bases", json={"name": "测试"}).json()["id"]
    base = f"/api/knowledge-bases/{kb_id}"
    entry = client.post(base + "/qa-pairs", json={"question": "Q", "answer": "A"}).json()
    from app import api_routes

    read_document = api_routes._require_document

    def read_then_delete(database_path, selected_kb, document_id, version_no=None):
        result = read_document(database_path, selected_kb, document_id, version_no)
        delete_document(database_path, selected_kb, document_id)
        return result

    monkeypatch.setattr(api_routes, "_require_document", read_then_delete)
    response = client.put(base + "/qa-pairs/" + entry["document_id"], json={"question": "Q", "answer": "B"})
    assert response.status_code == 404
    assert client.get(base + "/documents").json() == []
