"""Read the first supported document formats without guessing bad encodings."""

from pathlib import Path


SUPPORTED_TEXT_SUFFIXES = {".md", ".txt"}


class DocumentParseError(ValueError):
    """The selected file cannot be used as a text document."""


def parse_text_document(path: Path) -> str:
    """Return UTF-8 text from an MD/TXT file, or explain why it cannot be read."""
    if path.suffix.lower() not in SUPPORTED_TEXT_SUFFIXES:
        raise DocumentParseError(f"Unsupported file type: {path.suffix or '(none)'}")
    try:
        data = path.read_bytes()
    except OSError as exc:
        raise DocumentParseError(f"Cannot read {path.name}: {exc}") from exc

    return parse_text_bytes(path.name, data)


def parse_text_bytes(filename: str, data: bytes) -> str:
    """Parse one upload or local file using the same rules."""
    if Path(filename).suffix.lower() not in SUPPORTED_TEXT_SUFFIXES:
        raise DocumentParseError(
            f"Unsupported file type: {Path(filename).suffix or '(none)'}"
        )

    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise DocumentParseError(
            f"Cannot decode {filename} as UTF-8; check its encoding"
        ) from exc

    # Keep search/citation line positions consistent on Windows and Unix.
    text = text.replace("\r\n", "\n").replace("\r", "\n")

    if not text.strip():
        raise DocumentParseError(f"Document is empty: {filename}")

    return text
