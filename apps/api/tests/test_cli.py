"""Exercise the commands a teammate will actually type."""

import sqlite3

from app.cli import main


def test_cli_create_import_and_list(tmp_path, capsys) -> None:
    database = tmp_path / "knowledge.sqlite3"
    source_folder = tmp_path / "docs"
    source_folder.mkdir()
    (source_folder / "readme.md").write_text("# Hello", encoding="utf-8")
    database_arg = ["--db", str(database)]

    assert main(database_arg + ["kb", "create", "--name", "Demo"]) == 0
    kb_id = capsys.readouterr().out.strip().split()[-1]

    assert main(database_arg + ["kb", "list"]) == 0
    assert kb_id in capsys.readouterr().out

    assert (
        main(
            database_arg
            + [
                "import", "--kb", kb_id, "--dir", str(source_folder),
            ]
        )
        == 0
    )
    assert "CREATED\treadme.md\tv1" in capsys.readouterr().out

    assert main(database_arg + ["docs", "list", "--kb", kb_id]) == 0
    assert "readme.md\tv1" in capsys.readouterr().out

    assert main(database_arg + ["chunks", "list", "--kb", kb_id]) == 0
    assert "readme.md\tv1\tchunk 1\tL1-L1" in capsys.readouterr().out

    assert main(database_arg + ["search", "--kb", kb_id, "--query", "hello"]) == 0
    assert "readme.md v1 L1-L1" in capsys.readouterr().out

    assert main(database_arg + ["search", "--kb", kb_id, "--query", "missing"]) == 0
    assert "No matching source chunks found." in capsys.readouterr().out

    # The team's chosen default keeps a byte-for-byte original copy.
    with sqlite3.connect(database) as connection:
        saved_bytes = connection.execute(
            "SELECT original_bytes FROM document_versions"
        ).fetchone()[0]
    assert saved_bytes == b"# Hello"
