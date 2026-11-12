"""Extract normalized text from the document formats accepted by imports."""

from io import BytesIO
from pathlib import Path

from docx import Document
from docx.text.paragraph import Paragraph
from openpyxl import load_workbook
from pypdf import PdfReader


_UTF8_SUFFIXES = {".md", ".txt"}


class DocumentParseError(ValueError):
    """The selected file cannot be used as a text document."""


def _word_text(source: BytesIO) -> str:
    lines = []
    for block in Document(source).iter_inner_content():
        if isinstance(block, Paragraph):
            lines.append(block.text)
        else:
            for row in block.rows:
                lines.append("\t".join(cell.text for cell in row.cells))
    return "\n".join(lines)


def _excel_text(source: BytesIO) -> str:
    book = load_workbook(source, read_only=True, data_only=True)
    sections = []
    try:
        for sheet in book.worksheets:
            sheet.reset_dimensions()
            rows = []
            for values in sheet.iter_rows(values_only=True):
                row = "\t".join("" if value is None else str(value) for value in values)
                if row.strip():
                    rows.append(row)
            if rows:
                sections.append(f"工作表：{sheet.title}\n" + "\n".join(rows))
    finally:
        book.close()
    return "\n\n".join(sections)


def _pdf_text(source: BytesIO) -> str:
    reader = PdfReader(source)
    if reader.is_encrypted:
        raise DocumentParseError("PDF is encrypted; remove the protection before importing")
    sections = []
    for page_number, page in enumerate(reader.pages, start=1):
        text = page.extract_text().strip()
        if text:
            sections.append(f"PDF 第 {page_number} 页\n{text}")
    if not sections:
        raise DocumentParseError("PDF has no extractable text; run OCR on scanned pages before importing")
    return "\n\n".join(sections)


_BINARY_PARSERS = {".docx": _word_text, ".xlsx": _excel_text, ".pdf": _pdf_text}
SUPPORTED_DOCUMENT_SUFFIXES = _UTF8_SUFFIXES | _BINARY_PARSERS.keys()


def parse_text_document(path: Path) -> str:
    """Return normalized text from a local file."""
    if path.suffix.lower() not in SUPPORTED_DOCUMENT_SUFFIXES:
        raise DocumentParseError(f"Unsupported file type: {path.suffix or '(none)'}")
    try:
        data = path.read_bytes()
    except OSError as exc:
        raise DocumentParseError(f"Cannot read {path.name}: {exc}") from exc

    return parse_text_bytes(path.name, data)


def parse_text_bytes(filename: str, data: bytes) -> str:
    """Parse one upload or local file using the same rules."""
    suffix = Path(filename).suffix.lower()
    if suffix in _UTF8_SUFFIXES:
        try:
            text = data.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise DocumentParseError(
                f"Cannot decode {filename} as UTF-8; check its encoding"
            ) from exc
    elif suffix in _BINARY_PARSERS:
        try:
            text = _BINARY_PARSERS[suffix](BytesIO(data))
        except DocumentParseError:
            raise
        except Exception as exc:
            # Malformed containers can fail at several layers of a format library.
            raise DocumentParseError(f"Cannot parse {filename} as {suffix[1:].upper()}") from exc
    else:
        raise DocumentParseError(f"Unsupported file type: {suffix or '(none)'}")

    # Keep search/citation line positions consistent on Windows and Unix.
    text = text.replace("\r\n", "\n").replace("\r", "\n")

    if not text.strip():
        raise DocumentParseError(f"Document is empty: {filename}")

    return text
