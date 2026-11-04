"""The answer endpoint uses retrieved evidence without changing question v1."""

import pytest
from fastapi.testclient import TestClient

from app.answer_generation import GeneratedAnswer
from app.config import get_database_path
from app.main import app


@pytest.fixture
def client(tmp_path):
    app.dependency_overrides[get_database_path] = lambda: tmp_path / "answers.sqlite3"
    try:
        with TestClient(app) as http:
            yield http
    finally:
        app.dependency_overrides.clear()


def _base_with_document(http: TestClient) -> str:
    response = http.post("/api/knowledge-bases", json={"name": "课程资料"})
    assert response.status_code == 201
    kb_id = response.json()["id"]
    upload = http.post(
        f"/api/knowledge-bases/{kb_id}/documents/import",
        files={"files": ("guide.md", "# Trace\nTrace 页面显示调用记录。".encode(), "text/markdown")},
    )
    assert upload.status_code == 200
    return kb_id


def test_answer_returns_model_text_and_current_source(client, monkeypatch) -> None:
    kb_id = _base_with_document(client)

    def fake_generation(question, hits):
        assert question == "Trace 在哪里看？"
        assert len(hits) == 1
        return GeneratedAnswer("在 Trace 页面查看调用记录。", "generated", hits)

    monkeypatch.setattr("app.api_routes.generate_answer", fake_generation)
    response = client.post(
        f"/api/knowledge-bases/{kb_id}/answers",
        json={"question": "  Trace 在哪里看？  "},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["answer_status"] == "generated"
    assert body["answer"] == "在 Trace 页面查看调用记录。"
    assert body["model"] == "qwen3.7-plus"
    assert len(body["citations"]) == 1
    assert body["citations"][0]["relative_path"] == "guide.md"
    assert body["citations"][0]["version_no"] == 1

    original = client.post(
        f"/api/knowledge-bases/{kb_id}/questions", json={"question": "Trace"}
    )
    assert original.status_code == 200
    assert original.json()["answer_status"] == "not_generated"


def test_no_match_refuses_without_model_key(client, monkeypatch) -> None:
    kb_id = _base_with_document(client)
    monkeypatch.delenv("DASHSCOPE_API_KEY", raising=False)
    response = client.post(
        f"/api/knowledge-bases/{kb_id}/answers", json={"question": "月光电梯"}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["answer_status"] == "insufficient_evidence"
    assert body["citations"] == []
    assert body["model"] is None


def test_missing_key_and_invalid_requests(client, monkeypatch) -> None:
    kb_id = _base_with_document(client)
    monkeypatch.delenv("DASHSCOPE_API_KEY", raising=False)
    url = f"/api/knowledge-bases/{kb_id}/answers"
    assert client.post(url, json={"question": "Trace"}).status_code == 503
    assert client.post(url, json={"question": "   "}).status_code == 422
    assert client.post(url, json={"question": "Trace", "limit": 9}).status_code == 422
    assert client.post(
        "/api/knowledge-bases/missing/answers", json={"question": "Trace"}
    ).status_code == 404
