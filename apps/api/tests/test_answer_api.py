"""The answer endpoint uses retrieved evidence without changing question v1."""

from pathlib import Path

import httpx
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

    def fake_generation(question, hits, *, history):
        assert question == "Trace 在哪里看？"
        assert history == []
        assert len(hits) == 1
        return GeneratedAnswer("在 Trace 页面查看调用记录。", "generated", hits, ["S1"])

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
    assert body["citations"][0]["label"] == "S1"

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


def test_broad_question_delivers_experiment_entry_to_model_without_rewriting_question(client, monkeypatch) -> None:
    kb_id = client.post("/api/knowledge-bases", json={"name": "公开资料"}).json()["id"]
    docs = Path(__file__).resolve().parents[3] / "evals" / "agent_insight" / "docs"
    upload = client.post(
        f"/api/knowledge-bases/{kb_id}/documents/import",
        files=[("files", (path.name, path.read_bytes(), "text/markdown")) for path in sorted(docs.glob("*.md"))],
    )
    assert upload.json()["failed"] == 0

    def fake_generation(question, hits, *, history):
        assert question == "Agent Insight 如何管理实验？"
        label, hit = next(
            (f"S{index}", hit) for index, hit in enumerate(hits, start=1)
            if hit.chunk.relative_path == "experiments.md"
            and "可以查看当前账号下的实验记录" in hit.chunk.content
        )
        return GeneratedAnswer("进入评估与实验中的实验页面。", "generated", [hit], [label])

    monkeypatch.setattr("app.api_routes.generate_answer", fake_generation)
    response = client.post(
        f"/api/knowledge-bases/{kb_id}/answers",
        json={"question": "Agent Insight 如何管理实验？"},
    )
    assert response.status_code == 200
    assert response.json()["citations"][0]["start_line"] == 10
    follow_up = client.post(
        f"/api/knowledge-bases/{kb_id}/questions",
        json={
            "question": "刚才那个实验失败后怎么重试？",
            "history": ["Agent Insight 如何管理实验？"],
        },
    )
    assert follow_up.status_code == 200
    assert any(
        "选择已有 Trace 的实验保留当前 Trace，只重试失败评估" in hit["content"]
        for hit in follow_up.json()["matches"]
    )


def test_follow_up_uses_recent_topic_for_retrieval_and_model_context(client, monkeypatch) -> None:
    kb_id = _base_with_document(client)
    base = f"/api/knowledge-bases/{kb_id}"
    question = "它在哪里？"
    history = ["星图是什么？", "Trace 是什么？", "刚才那个有什么用？"]
    assert client.post(f"{base}/questions", json={"question": question}).json()["matches"] == []
    request = {"question": question, "history": history}
    found = client.post(f"{base}/questions", json=request).json()
    assert found["question"] == question
    assert found["matches"][0]["relative_path"] == "guide.md"

    monkeypatch.setenv("DASHSCOPE_API_KEY", "test-only-key")
    calls = []

    def fake_post(url, *, headers, json, timeout):
        calls.append(url)
        messages = json["messages"]
        assert "须依据本次资料片段" in messages[0]["content"]
        assert '"Trace 是什么？", "刚才那个有什么用？"' in messages[1]["content"]
        assert "星图" not in messages[1]["content"]
        assert f"问题：{question}" in messages[1]["content"]
        assert "[S1] guide.md" in messages[1]["content"]
        return httpx.Response(
            200,
            request=httpx.Request("POST", url),
            json={"choices": [{
                "finish_reason": "stop",
                "message": {"content": '{"status":"generated","answer":"在 Trace 页面查看。","citation_ids":["S1"]}'},
            }]},
        )

    monkeypatch.setattr("app.answer_generation.httpx.post", fake_post)
    response = client.post(f"{base}/answers", json=request)
    assert response.status_code == 200
    assert response.json()["citations"][0]["chunk_id"] == found["matches"][0]["chunk_id"]
    unrelated = {"question": "月光电梯", "history": history}
    assert client.post(f"{base}/questions", json=unrelated).json()["matches"] == []
    assert client.post(f"{base}/answers", json=unrelated).json()["answer_status"] == "insufficient_evidence"
    assert len(calls) == 1


@pytest.mark.parametrize("endpoint", ["questions", "answers"])
@pytest.mark.parametrize("history", [["Trace"] * 4, ["  "], ["a" * 1001]])
def test_history_rejects_oversized_or_blank_questions(client, endpoint, history) -> None:
    kb_id = _base_with_document(client)
    response = client.post(
        f"/api/knowledge-bases/{kb_id}/{endpoint}",
        json={"question": "它在哪里？", "history": history},
    )
    assert response.status_code == 422


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
