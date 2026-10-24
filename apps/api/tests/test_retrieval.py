"""Check ranking, source isolation, active versions, and no-evidence behavior."""

import pytest

from app.knowledge_store import create_knowledge_base, import_document
from app.retrieval import search_knowledge_base, tokenize


def test_tokenizer_handles_chinese_pairs_and_case_insensitive_latin() -> None:
    assert tokenize("登录失败 Error E102") == [
        "登录", "录失", "失败", "error", "e102"
    ]


def test_keyword_search_prefers_matching_document(tmp_path) -> None:
    database = tmp_path / "knowledge.sqlite3"
    kb_id = create_knowledge_base(database, "A")
    import_document(
        database, kb_id, "login.md", "# 登录失败\n请检查密码。".encode(),
        retain_original=True,
    )
    import_document(
        database, kb_id, "admin.md", "# 管理员权限\n请联系管理员。".encode(),
        retain_original=True,
    )

    hits = search_knowledge_base(database, kb_id, "登录失败")
    assert hits[0].chunk.relative_path == "login.md"
    assert hits[0].chunk.start_line == 1
    assert hits[0].score > 0


def test_search_does_not_cross_knowledge_bases_or_use_old_versions(tmp_path) -> None:
    database = tmp_path / "knowledge.sqlite3"
    first_kb = create_knowledge_base(database, "A")
    second_kb = create_knowledge_base(database, "B")
    import_document(
        database, first_kb, "guide.txt", "旧版专有术语".encode(),
        retain_original=True,
    )
    import_document(
        database, second_kb, "private.txt", "新版专有术语".encode(),
        retain_original=True,
    )

    assert search_knowledge_base(database, first_kb, "新版") == []
    assert [hit.chunk.relative_path for hit in search_knowledge_base(database, second_kb, "新版")] == [
        "private.txt"
    ]

    import_document(
        database, first_kb, "guide.txt", "当前只有安装说明".encode(),
        retain_original=True,
    )
    assert search_knowledge_base(database, first_kb, "旧版") == []


def test_exact_error_code_and_missing_evidence(tmp_path) -> None:
    database = tmp_path / "knowledge.sqlite3"
    kb_id = create_knowledge_base(database, "A")
    import_document(
        database, kb_id, "errors.md", b"Error E102 means retry login.",
        retain_original=True,
    )

    assert search_knowledge_base(database, kb_id, "e102")[0].chunk.relative_path == "errors.md"
    assert search_knowledge_base(database, kb_id, "E999") == []


@pytest.mark.parametrize("query,limit", [(" ", 5), ("test", 0), ("test", 21)])
def test_rejects_invalid_search_input(tmp_path, query, limit) -> None:
    with pytest.raises(ValueError):
        search_knowledge_base(tmp_path / "empty.sqlite3", "kb_missing", query, limit=limit)


def test_unknown_knowledge_base_is_not_reported_as_no_matches(tmp_path) -> None:
    with pytest.raises(ValueError, match="Unknown knowledge base"):
        search_knowledge_base(tmp_path / "empty.sqlite3", "kb_missing", "login")
