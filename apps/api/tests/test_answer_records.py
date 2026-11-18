"""Only final answers become durable, knowledge-base-scoped feedback targets."""

import json

import pytest
from fastapi.testclient import TestClient

from app.answer_generation import GeneratedAnswer, ModelAnswerError
from app.config import get_database_path
from app.knowledge_store import delete_document
from app.main import app


@pytest.fixture
def client(tmp_path):
    database = tmp_path / "records.sqlite3"
    app.dependency_overrides[get_database_path] = lambda: database
    try:
        with TestClient(app) as http:
            yield http, database
    finally:
        app.dependency_overrides.clear()


def test_final_snapshots_feedback_retries_review_filter_and_isolation(client, monkeypatch):
    http, database = client
    kb_id = http.post("/api/knowledge-bases", json={"name": "测试"}).json()["id"]
    base = f"/api/knowledge-bases/{kb_id}"
    http.post(base + "/documents/import", files={"files": ("trace.txt", b"Trace guide")})

    def generate(question, hits, *, history):
        return GeneratedAnswer("查看 Trace。", "generated", hits, ["S1"])

    monkeypatch.setattr("app.api_routes.generate_answer", generate)
    response = http.post(base + "/answers", json={"question": "Trace", "history": ["Trace 是什么"]})
    assert response.status_code == 200
    answer = response.json()
    answer_id = answer["answer_id"]
    assert answer_id.startswith("ans_")
    feedback_url = base + f"/answers/{answer_id}/feedback"
    for _ in range(2):
        feedback = http.put(feedback_url, json={"rating": "unhelpful", "comment": " 缺少步骤 "})
        assert feedback.status_code == 204 and feedback.content == b""
    records = http.get(base + "/answer-records?needs_review=true").json()
    assert len(records) == 1
    assert records[0]["response"] == answer
    assert records[0]["comment"] == "缺少步骤"
    assert records[0]["history"] == ["Trace 是什么"]
    document_id = http.get(base + "/documents").json()[0]["id"]
    delete_document(database, kb_id, document_id)
    assert http.get(base + "/answer-records").json()[0]["response"]["citations"] == answer["citations"]
    http.put(feedback_url, json={"rating": "helpful"})
    assert http.get(base + "/answer-records?needs_review=true").json() == []
    assert len(http.get(base + "/answer-records").json()) == 1
    other = http.post("/api/knowledge-bases", json={"name": "别的库"}).json()["id"]
    assert http.put(f"/api/knowledge-bases/{other}/answers/{answer_id}/feedback", json={"rating": "helpful"}).status_code == 404
    assert http.get(f"/api/knowledge-bases/{other}/answer-records").json() == []
    assert http.put(feedback_url, json={"rating": "unknown"}).status_code == 422
    assert http.get(base + "/answer-records?limit=101").status_code == 422
    assert http.get(base + "/answer-records?offset=-1").status_code == 422


def test_unanswered_stream_is_recorded_but_failed_preview_is_not(client, monkeypatch):
    http, _ = client
    kb_id = http.post("/api/knowledge-bases", json={"name": "测试"}).json()["id"]
    base = f"/api/knowledge-bases/{kb_id}"
    monkeypatch.delenv("DASHSCOPE_API_KEY", raising=False)
    stream = http.post(base + "/answers/stream", json={"question": "没有的资料"})
    final = json.loads(stream.text.split("data: ", 1)[1])
    records = http.get(base + "/answer-records?needs_review=true").json()
    assert len(records) == 1
    assert final == records[0]["response"]
    assert final["answer_status"] == "insufficient_evidence"

    async def failing_stream(question, hits, *, history):
        yield "半截预览"
        raise ModelAnswerError("upstream disconnected")

    monkeypatch.setattr("app.api_routes.stream_answer", failing_stream)
    failed = http.post(base + "/answers/stream", json={"question": "断流测试"})
    assert "event: error" in failed.text and "event: final" not in failed.text
    assert len(http.get(base + "/answer-records").json()) == 1
    assert http.get(base + "/answer-records?limit=1&offset=1").json() == []
