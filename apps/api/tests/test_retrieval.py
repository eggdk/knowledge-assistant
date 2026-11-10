"""Check ranking, source isolation, active versions, and no-evidence behavior."""

import pytest

from app.knowledge_store import create_knowledge_base, import_document
from app.retrieval import (
    _matches_document_title,
    _retrieval_query,
    _search_words,
    search_knowledge_base,
    tokenize,
)


def test_tokenizer_handles_chinese_pairs_and_case_insensitive_latin() -> None:
    assert tokenize("登录失败 Error E102") == [
        "登录", "录失", "失败", "error", "e102"
    ]


def test_second_channel_keeps_chinese_words_without_cross_word_pair() -> None:
    assert _search_words("登录失败 Error E102") == [
        "登录", "失败", "error", "e102"
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


def test_question_cleanup_preserves_specific_actions_codes_and_negation() -> None:
    assert _retrieval_query("如何删除 E102 记录，但不要删除历史？") == "删除 E102 记录，但不要删除历史？"
    assert _retrieval_query("怎么使用API v2？") == "API v2？"
    assert _retrieval_query("如何管理") == "如何管理"


def test_title_matching_respects_full_title_and_ascii_word_boundaries() -> None:
    assert _matches_document_title("实验怎么管理？", "实验 / 实验列表")
    assert _matches_document_title("如何使用 api？", "API / 安装")
    assert not _matches_document_title("myapiclient", "API / 安装")
    assert not _matches_document_title("管理权限", "权限管理 / 介绍")


@pytest.mark.parametrize("query", ["北斗系统如何管理预约？", "如何管理预约？", "预约怎么管理？"])
def test_overview_questions_find_evidence_in_a_different_domain(tmp_path, query) -> None:
    database = tmp_path / "appointments.sqlite3"
    kb_id = create_knowledge_base(database, "预约资料")
    text = "# 预约\n## 预约列表\n从服务菜单打开预约列表，查看和修改预约。"
    import_document(database, kb_id, "booking.md", text.encode(), retain_original=True)
    import_document(
        database, kb_id, "trace.md",
        "# 如何关联任务\n北斗系统关联任务编号，管理员可查看关联记录。".encode(),
        retain_original=True,
    )
    for index in range(6):
        import_document(
            database, kb_id, f"other-{index}.md",
            f"# 如何关联记录{index}\n后台任务按记录号关联，管理员查询关联状态。".encode(),
            retain_original=True,
        )
    hits = search_knowledge_base(database, kb_id, query, limit=5)
    hit = next(hit for hit in hits if "查看和修改预约" in hit.chunk.content)
    assert hit.chunk.relative_path == "booking.md"
    assert text[hit.chunk.start_offset:hit.chunk.end_offset] == hit.chunk.content
