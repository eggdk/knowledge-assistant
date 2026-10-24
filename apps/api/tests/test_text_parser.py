"""First file-format tests; no database or model service is needed."""

import pytest

from app.text_parser import DocumentParseError, parse_text_document


def test_reads_chinese_markdown(tmp_path) -> None:
    source = tmp_path / "使用说明.md"
    source.write_text("# 标题\n这里是正文。\n", encoding="utf-8")

    assert parse_text_document(source) == "# 标题\n这里是正文。\n"


def test_reads_txt_with_utf8_bom(tmp_path) -> None:
    source = tmp_path / "notes.txt"
    source.write_bytes(b"\xef\xbb\xbf" + "第一行\n第二行".encode("utf-8"))

    assert parse_text_document(source) == "第一行\n第二行"


def test_rejects_unsupported_format(tmp_path) -> None:
    source = tmp_path / "report.pdf"
    source.write_bytes(b"%PDF")

    with pytest.raises(DocumentParseError, match="Unsupported file type"):
        parse_text_document(source)


def test_reports_non_utf8_text(tmp_path) -> None:
    source = tmp_path / "legacy.txt"
    source.write_bytes(b"\xff\xfe\xfa")

    with pytest.raises(DocumentParseError, match="Cannot decode"):
        parse_text_document(source)


def test_rejects_empty_document(tmp_path) -> None:
    source = tmp_path / "empty.md"
    source.write_text(" \n\t", encoding="utf-8")

    with pytest.raises(DocumentParseError, match="Document is empty"):
        parse_text_document(source)
