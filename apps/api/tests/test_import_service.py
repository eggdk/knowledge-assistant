"""Directory import is partial, repeatable, and explicit about failures."""

from app.import_service import import_directory
from app.knowledge_store import create_knowledge_base, list_documents


def test_import_is_repeatable_and_never_deletes_absent_files(tmp_path) -> None:
    database = tmp_path / "knowledge.sqlite3"
    folder = tmp_path / "sources"
    folder.mkdir()
    first = folder / "first.md"
    second = folder / "second.txt"
    first.write_text("First", encoding="utf-8")
    second.write_text("Second", encoding="utf-8")
    kb_id = create_knowledge_base(database, "Course")

    initial = import_directory(database, kb_id, folder, retain_original=False)
    again = import_directory(database, kb_id, folder, retain_original=False)
    second.unlink()
    first.write_text("Updated", encoding="utf-8")
    changed = import_directory(database, kb_id, folder, retain_original=False)

    assert [outcome.status for outcome in initial] == ["created", "created"]
    assert [outcome.status for outcome in again] == ["unchanged", "unchanged"]
    assert [(outcome.status, outcome.version_no) for outcome in changed] == [
        ("updated", 2)
    ]
    assert list_documents(database, kb_id) == [("first.md", 2), ("second.txt", 1)]


def test_bad_file_does_not_block_good_file(tmp_path) -> None:
    database = tmp_path / "knowledge.sqlite3"
    folder = tmp_path / "sources"
    folder.mkdir()
    (folder / "bad.txt").write_bytes(b"\xff")
    (folder / "good.md").write_bytes(b"Good")
    kb_id = create_knowledge_base(database, "Course")

    outcomes = import_directory(database, kb_id, folder, retain_original=True)

    assert [outcome.status for outcome in outcomes] == ["failed", "created"]
    assert "Cannot decode" in outcomes[0].error
    assert list_documents(database, kb_id) == [("good.md", 1)]
