"""The CLI must only see supported files under the selected root."""

import pytest

from app.directory_scan import DirectoryScanError, scan_text_documents


def test_scans_nested_supported_files_in_stable_order(tmp_path) -> None:
    (tmp_path / "b.txt").write_text("B", encoding="utf-8")
    nested = tmp_path / "folder"
    nested.mkdir()
    (nested / "a.MD").write_text("A", encoding="utf-8")
    (nested / "ignored.pdf").write_bytes(b"%PDF")

    result = scan_text_documents(tmp_path)

    assert [relative for relative, _ in result] == ["b.txt", "folder/a.MD"]
    assert all(path.is_absolute() for _, path in result)


def test_rejects_a_missing_directory(tmp_path) -> None:
    with pytest.raises(DirectoryScanError, match="Not a directory"):
        scan_text_documents(tmp_path / "missing")


def test_rejects_symlink_file_when_supported(tmp_path) -> None:
    source = tmp_path / "source.md"
    source.write_text("text", encoding="utf-8")
    link = tmp_path / "link.md"
    try:
        link.symlink_to(source)
    except (OSError, NotImplementedError):
        pytest.skip("Symlinks are unavailable on this Windows account")

    with pytest.raises(DirectoryScanError, match="Symlink file"):
        scan_text_documents(tmp_path)
