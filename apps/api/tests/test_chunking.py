"""Chunk text without losing its connection to the original document."""

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
