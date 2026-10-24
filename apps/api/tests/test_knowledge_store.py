"""Versioning and isolation tests use a real temporary SQLite database."""

import hashlib
import sqlite3

import pytest

from app.knowledge_store import (
    create_knowledge_base,
    import_document,
    list_active_chunks,
    list_documents,
    list_knowledge_bases,
)
from app.text_parser import DocumentParseError


def test_create_base_then_import_update_and_skip_same_bytes(tmp_path) -> None:
    database = tmp_path / "knowledge.sqlite3"
    kb_id = create_knowledge_base(database, "课程资料")
    assert list_knowledge_bases(database) == [(kb_id, "课程资料")]

    first = import_document(
        database, kb_id, "guide/intro.md", b"# Hello", retain_original=True
    )
    unchanged = import_document(
        database, kb_id, "guide/intro.md", b"# Hello", retain_original=True
    )
    updated = import_document(
        database, kb_id, "guide/intro.md", "# 中文".encode(), retain_original=True
    )

    assert (first.status, first.version_no) == ("created", 1)
    assert (unchanged.status, unchanged.version_no) == ("unchanged", 1)
    assert (updated.status, updated.version_no) == ("updated", 2)
    assert list_documents(database, kb_id) == [("guide/intro.md", 2)]

    with sqlite3.connect(database) as connection:
        versions = connection.execute(
            "SELECT version_no, content, original_bytes FROM document_versions ORDER BY version_no"
        ).fetchall()
    assert versions == [(1, "# Hello", b"# Hello"), (2, "# 中文", "# 中文".encode())]


def test_original_copy_can_be_omitted(tmp_path) -> None:
    database = tmp_path / "knowledge.sqlite3"
    kb_id = create_knowledge_base(database, "课程资料")
    import_document(database, kb_id, "note.txt", b"hello", retain_original=False)

    with sqlite3.connect(database) as connection:
        row = connection.execute(
            "SELECT content, original_bytes FROM document_versions"
        ).fetchone()
    assert row == ("hello", None)

    # Choosing "copy" later can fill the missing original without a fake new version.
    repeated = import_document(
        database, kb_id, "note.txt", b"hello", retain_original=True
    )
    assert (repeated.status, repeated.version_no) == ("unchanged", 1)
    with sqlite3.connect(database) as connection:
        copied = connection.execute(
            "SELECT original_bytes FROM document_versions"
        ).fetchone()
    assert copied == (b"hello",)


def test_two_knowledge_bases_do_not_share_documents(tmp_path) -> None:
    database = tmp_path / "knowledge.sqlite3"
    first_kb = create_knowledge_base(database, "A")
    second_kb = create_knowledge_base(database, "B")
    import_document(database, first_kb, "same.md", b"A", retain_original=False)
    import_document(database, second_kb, "same.md", b"B", retain_original=False)

    assert list_documents(database, first_kb) == [("same.md", 1)]
    assert list_documents(database, second_kb) == [("same.md", 1)]
    assert [chunk.content for chunk in list_active_chunks(database, first_kb)] == ["A"]
    assert [chunk.content for chunk in list_active_chunks(database, second_kb)] == ["B"]


def test_chunks_keep_exact_source_location_and_only_active_version_is_listed(tmp_path) -> None:
    database = tmp_path / "knowledge.sqlite3"
    kb_id = create_knowledge_base(database, "A")
    first_text = "# 总览\n第一段。\n\n## 安装\n第二段。\n"
    import_document(
        database, kb_id, "manual.md", first_text.encode(), retain_original=True
    )
    first_chunks = list_active_chunks(database, kb_id)

    assert [(chunk.heading, chunk.start_line, chunk.end_line) for chunk in first_chunks] == [
        ("总览", 1, 2),
        ("总览 / 安装", 4, 5),
    ]
    assert all(
        first_text[chunk.start_offset : chunk.end_offset] == chunk.content
        and chunk.content_hash == hashlib.sha256(chunk.content.encode()).hexdigest()
        for chunk in first_chunks
    )

    import_document(
        database, kb_id, "manual.md", b"# New\nUpdated", retain_original=True
    )
    active = list_active_chunks(database, kb_id)
    assert len(active) == 1
    assert (active[0].version_no, active[0].content) == (2, "# New\nUpdated")
    with sqlite3.connect(database) as connection:
        all_versions = connection.execute(
            "SELECT DISTINCT version_no FROM document_chunks ORDER BY version_no"
        ).fetchall()
    assert all_versions == [(1,), (2,)]


def test_unchanged_import_backfills_chunks_for_older_database(tmp_path) -> None:
    database = tmp_path / "knowledge.sqlite3"
    kb_id = create_knowledge_base(database, "A")
    import_document(database, kb_id, "old.txt", b"Old data", retain_original=True)
    with sqlite3.connect(database) as connection:
        connection.execute("DROP TABLE document_chunks")

    result = import_document(
        database, kb_id, "old.txt", b"Old data", retain_original=True
    )
    assert (result.status, result.version_no) == ("unchanged", 1)
    assert [chunk.content for chunk in list_active_chunks(database, kb_id)] == [
        "Old data"
    ]


def test_chunk_write_failure_does_not_activate_a_new_version(tmp_path, monkeypatch) -> None:
    database = tmp_path / "knowledge.sqlite3"
    kb_id = create_knowledge_base(database, "A")
    import_document(database, kb_id, "same.txt", b"Good", retain_original=True)

    def fail_chunk_write(*_args):
        raise RuntimeError("simulated chunk write failure")

    monkeypatch.setattr("app.knowledge_store._insert_chunks", fail_chunk_write)
    with pytest.raises(RuntimeError, match="simulated"):
        import_document(database, kb_id, "same.txt", b"New", retain_original=True)

    assert list_documents(database, kb_id) == [("same.txt", 1)]
    with sqlite3.connect(database) as connection:
        versions = connection.execute(
            "SELECT version_no FROM document_versions ORDER BY version_no"
        ).fetchall()
    assert versions == [(1,)]


def test_bad_update_does_not_replace_active_version(tmp_path) -> None:
    database = tmp_path / "knowledge.sqlite3"
    kb_id = create_knowledge_base(database, "A")
    import_document(database, kb_id, "same.md", b"Good", retain_original=False)

    with pytest.raises(DocumentParseError, match="Cannot decode"):
        import_document(database, kb_id, "same.md", b"\xff", retain_original=False)

    assert list_documents(database, kb_id) == [("same.md", 1)]


@pytest.mark.parametrize(
    "bad_path", ["../escape.md", "/absolute.md", "a\\b.md", "./a.md", "C:/a.md"]
)
def test_rejects_unsafe_relative_paths(tmp_path, bad_path) -> None:
    database = tmp_path / "knowledge.sqlite3"
    kb_id = create_knowledge_base(database, "A")
    with pytest.raises(ValueError, match="safe relative"):
        import_document(database, kb_id, bad_path, b"text", retain_original=False)
