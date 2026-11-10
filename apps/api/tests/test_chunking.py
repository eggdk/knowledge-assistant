"""Chunk text without losing its connection to the original document."""

from pathlib import Path
import re

import pytest

from app.chunking import split_text_into_chunks


def test_markdown_heading_paths_and_line_ranges() -> None:
    content = "# 总览\n第一段。\n\n## 安装\n第二段。\n"

    chunks = split_text_into_chunks(content, ".md")

    assert [(part.heading, part.start_line, part.end_line) for part in chunks] == [
        ("总览", 1, 2),
        ("总览 / 安装", 4, 5),
    ]
    assert all(content[part.start_offset : part.end_offset] == part.text for part in chunks)


def test_long_paragraph_is_bounded_and_overlaps() -> None:
    content = "甲" * 1000
    chunks = split_text_into_chunks(
        content, ".txt", max_chars=300, min_chars=150, overlap_chars=40
    )

    assert len(chunks) > 3
    assert all(len(part.text) <= 300 for part in chunks)
    assert chunks[0].start_offset == 0
    assert chunks[-1].end_offset == len(content)
    assert all(
        previous.end_offset - current.start_offset == 40
        for previous, current in zip(chunks, chunks[1:])
    )


def test_heading_looking_line_inside_code_fence_is_not_a_section() -> None:
    content = "# 说明\n```md\n# 不是标题\n```\n正文。\n"
    chunks = split_text_into_chunks(content, ".md")
    assert len(chunks) == 1
    assert chunks[0].heading == "说明"
    assert "# 不是标题" in chunks[0].text


def test_markdown_heading_may_be_indented_by_three_spaces() -> None:
    content = "   # 标题\n正文。\n"
    chunks = split_text_into_chunks(content, ".md")
    assert len(chunks) == 1
    assert chunks[0].heading == "标题"


def test_paragraph_boundary_is_preferred_and_nonwhitespace_is_covered() -> None:
    content = "A" * 180 + "\n\n" + "B" * 180 + "\n\n" + "C" * 180
    chunks = split_text_into_chunks(
        content, ".txt", max_chars=400, min_chars=150, overlap_chars=30
    )

    assert len(chunks) >= 2
    assert chunks[0].text.endswith("B" * 10)
    assert all(
        any(part.start_offset <= position < part.end_offset for part in chunks)
        for position, character in enumerate(content)
        if not character.isspace()
    )


def test_rejects_invalid_chunk_parameters() -> None:
    with pytest.raises(ValueError, match="overlap_chars"):
        split_text_into_chunks("text", ".txt", max_chars=100, min_chars=50, overlap_chars=50)


@pytest.mark.parametrize("length", [1, 80, 250, 600, 601, 1000, 5000])
def test_no_nonwhitespace_character_is_lost_at_boundaries(length) -> None:
    content = "甲" * length
    chunks = split_text_into_chunks(content, ".txt")
    assert all(len(chunk.text) <= 600 for chunk in chunks)
    assert chunks[0].start_offset == 0
    assert chunks[-1].end_offset == len(content)
    assert all(
        next_chunk.start_offset <= previous.end_offset
        for previous, next_chunk in zip(chunks, chunks[1:])
    )


def test_real_retry_evidence_retains_the_complete_list_item() -> None:
    path = Path(__file__).resolve().parents[3] / "evals/agent_insight/docs/experiments.md"
    content = path.read_text(encoding="utf-8")
    chunks = split_text_into_chunks(content, ".md")
    evidence = [chunk for chunk in chunks if "只重试失败评估" in chunk.text]
    assert evidence
    assert all("选择已有 Trace 的实验保留当前 Trace" in chunk.text for chunk in evidence)
    assert not content[:chunks[0].start_offset].strip()
    assert not content[chunks[-1].end_offset:].strip()
    assert all(
        not content[previous.end_offset:current.start_offset].strip()
        for previous, current in zip(chunks, chunks[1:])
        if current.start_offset > previous.end_offset
    )
    for chunk in chunks:
        assert content[chunk.start_offset:chunk.end_offset] == chunk.text
        assert chunk.start_line == content[:chunk.start_offset].count("\n") + 1
        assert chunk.end_line == content[:chunk.end_offset - 1].count("\n") + 1
        assert len(chunk.text) <= 600
        for position in (chunk.start_offset, chunk.end_offset):
            assert not (
                0 < position < len(content)
                and re.fullmatch(r"[A-Za-z0-9_]{2}", content[position - 1:position + 1])
            )


def test_hard_limit_does_not_split_a_normal_ascii_word() -> None:
    content = "甲" * 265 + " Trace " + "乙" * 400
    chunks = split_text_into_chunks(
        content, ".txt", max_chars=270, min_chars=150, overlap_chars=40
    )
    assert any("Trace" in chunk.text for chunk in chunks)
    assert all(len(chunk.text) <= 270 for chunk in chunks)
    assert all(
        not re.fullmatch(r"[A-Za-z0-9_]{2}", content[p - 1:p + 1])
        for chunk in chunks for p in (chunk.start_offset, chunk.end_offset)
        if 0 < p < len(content)
    )


def test_overlong_single_identifier_remains_bounded_and_covered() -> None:
    content = "A" * 1600
    chunks = split_text_into_chunks(content, ".txt")
    assert all(0 < len(chunk.text) <= 600 for chunk in chunks)
    assert chunks[0].start_offset == 0
    assert chunks[-1].end_offset == len(content)
    assert all(a.start_offset < b.start_offset <= a.end_offset for a, b in zip(chunks, chunks[1:]))


def test_zero_overlap_does_not_add_context_from_previous_chunk() -> None:
    chunks = split_text_into_chunks("甲" * 1000, ".txt", overlap_chars=0)
    assert chunks[0].end_offset == chunks[1].start_offset
