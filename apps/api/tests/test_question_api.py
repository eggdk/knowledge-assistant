"""The first browser question contract returns evidence candidates only."""

import pytest
from fastapi.testclient import TestClient

from app.config import get_database_path
from app.main import app


@pytest.fixture
def client(tmp_path):
    app.dependency_overrides[get_database_path] = lambda: tmp_path / "questions.sqlite3"
    try:
        with TestClient(app) as http:
            yield http
    finally:
        app.dependency_overrides.clear()


def create_base(http: TestClient, name: str) -> str:
    response = http.post("/api/knowledge-bases", json={"name": name})
    assert response.status_code == 201
    return response.json()["id"]


def upload(http: TestClient, kb_id: str, content: str) -> None:
    response = http.post(
        f"/api/knowledge-bases/{kb_id}/documents/import",
        files={"files": ("guide.md", content.encode("utf-8"), "text/markdown")},
    )
    assert response.status_code == 200
    assert response.json()["failed"] == 0


def test_question_returns_current_source_without_claiming_an_answer(client) -> None:
    kb_id = create_base(client, "课程资料")
    upload(client, kb_id, "# 使用说明\n知识库支持导入 Markdown 文件。")

    response = client.post(
        f"/api/knowledge-bases/{kb_id}/questions",
        json={"question": "  Markdown 文件怎么导入？  "},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["question"] == "Markdown 文件怎么导入？"
    assert body["answer"] is None
    assert body["answer_status"] == "not_generated"
    assert len(body["matches"]) == 1
    match = body["matches"][0]
    assert match["chunk_id"].startswith("chk_")
    assert match["relative_path"] == "guide.md"
    assert match["version_no"] == 1
    assert match["start_line"] == 1
    assert "Markdown 文件" in match["content"]
    assert match["score"] > 0


def test_question_only_sees_its_knowledge_base_and_active_version(client) -> None:
    first = create_base(client, "第一个库")
    second = create_base(client, "第二个库")
    upload(client, first, "旧版独有词：月光电梯。")
    upload(client, first, "新版独有词：蓝色书签。")
    upload(client, second, "月光电梯只在另一个知识库。")

    url = f"/api/knowledge-bases/{first}/questions"
    old = client.post(url, json={"question": "月光电梯"})
    current = client.post(url, json={"question": "蓝色书签"})

    assert old.status_code == 200
    assert old.json()["matches"] == []
    assert old.json()["answer"] is None
    assert current.status_code == 200
    assert current.json()["matches"][0]["version_no"] == 2


def test_question_rejects_unknown_base_blank_question_and_bad_limit(client) -> None:
    kb_id = create_base(client, "测试库")
    assert client.post(
        "/api/knowledge-bases/missing/questions", json={"question": "内容"}
    ).status_code == 404
    assert client.post(
        f"/api/knowledge-bases/{kb_id}/questions", json={"question": "   "}
    ).status_code == 422
    assert client.post(
        f"/api/knowledge-bases/{kb_id}/questions",
        json={"question": "内容", "limit": 0},
    ).status_code == 422
