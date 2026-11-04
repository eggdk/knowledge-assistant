"""The model adapter accepts only cited, well-formed answers."""

import json

import httpx
import pytest

from app.answer_generation import ModelAnswerError, generate_answer
from app.knowledge_store import StoredChunk
from app.retrieval import SearchHit


def _hit() -> SearchHit:
    return SearchHit(
        chunk=StoredChunk(
            chunk_id="chk_example",
            kb_id="kb_example",
            document_id="doc_example",
            relative_path="guide.md",
            version_no=2,
            chunk_no=1,
            content="Trace 页面显示调用记录。",
            content_hash="hash",
            heading="Trace",
            start_offset=0,
            end_offset=15,
            start_line=1,
            end_line=2,
        ),
        score=1.0,
    )


def _provider_response(content: str) -> httpx.Response:
    return httpx.Response(
        200,
        request=httpx.Request("POST", "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"),
        json={
            "choices": [{"finish_reason": "stop", "message": {"content": content}}],
            "usage": {"prompt_tokens": 120, "completion_tokens": 35, "total_tokens": 155},
        },
    )


def test_model_receives_evidence_and_returns_only_retrieved_citation(monkeypatch) -> None:
    monkeypatch.setenv("DASHSCOPE_API_KEY", "test-only-key")
    monkeypatch.delenv("DASHSCOPE_BASE_URL", raising=False)

    def fake_post(url, *, headers, json, timeout):
        assert url.endswith("/chat/completions")
        assert headers["Authorization"] == "Bearer test-only-key"
        assert json["model"] == "qwen3.7-plus"
        assert json["enable_thinking"] is False
        assert json["max_tokens"] == 600
        assert json["response_format"] == {"type": "json_object"}
        assert "[S1] guide.md v2 L1-2" in json["messages"][1]["content"]
        assert timeout == 30.0
        return _provider_response(
            '{"status":"generated","answer":"在 Trace 页面查看。","citation_ids":["S1"]}'
        )

    monkeypatch.setattr("app.answer_generation.httpx.post", fake_post)
    answer = generate_answer("Trace 在哪里看？", [_hit()])
    assert answer.status == "generated"
    assert answer.answer == "在 Trace 页面查看。"
    assert [hit.chunk.chunk_id for hit in answer.cited_hits] == ["chk_example"]
    assert answer.citation_ids == ["S1"]
    assert answer.usage == {"prompt_tokens": 120, "completion_tokens": 35, "total_tokens": 155}


def test_model_cannot_cite_an_unretrieved_passage(monkeypatch) -> None:
    monkeypatch.setenv("DASHSCOPE_API_KEY", "test-only-key")
    monkeypatch.setattr(
        "app.answer_generation.httpx.post",
        lambda *args, **kwargs: _provider_response(
            json.dumps({"status": "generated", "answer": "答案", "citation_ids": ["S999"]})
        ),
    )
    with pytest.raises(ModelAnswerError, match="outside the retrieved set"):
        generate_answer("Trace 在哪里看？", [_hit()])


def test_inline_citation_must_be_in_the_returned_citation_list(monkeypatch) -> None:
    monkeypatch.setenv("DASHSCOPE_API_KEY", "test-only-key")
    monkeypatch.setattr(
        "app.answer_generation.httpx.post",
        lambda *args, **kwargs: _provider_response(
            '{"status":"generated","answer":"答案 [S2]","citation_ids":["S1"]}'
        ),
    )
    with pytest.raises(ModelAnswerError, match="missing from citation_ids"):
        generate_answer("Trace 在哪里看？", [_hit()])


def test_no_hits_never_calls_provider(monkeypatch) -> None:
    monkeypatch.delenv("DASHSCOPE_API_KEY", raising=False)
    monkeypatch.setattr(
        "app.answer_generation.httpx.post",
        lambda *args, **kwargs: pytest.fail("No model call expected"),
    )
    answer = generate_answer("无关问题", [])
    assert answer.status == "insufficient_evidence"
    assert answer.cited_hits == []
    assert answer.citation_ids == []
