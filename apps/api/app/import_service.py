"""Import selected local files through the same store future uploads will use."""

from dataclasses import dataclass
from pathlib import Path

from app.directory_scan import scan_text_documents
from app.knowledge_store import import_document, list_knowledge_bases
from app.text_parser import DocumentParseError


@dataclass(frozen=True)
class FileOutcome:
    relative_path: str
    status: str
    version_no: int | None = None
    error: str | None = None


def import_directory(
    database_path: Path,
    kb_id: str,
    directory: Path,
    *,
    retain_original: bool,
) -> list[FileOutcome]:
    """Import supported files; absent files never cause implicit deletion."""
    if kb_id not in {existing_id for existing_id, _ in list_knowledge_bases(database_path)}:
        raise ValueError(f"Unknown knowledge base: {kb_id}")

    outcomes: list[FileOutcome] = []
    for relative_path, source in scan_text_documents(directory):
        try:
            result = import_document(
                database_path,
                kb_id,
                relative_path,
                source.read_bytes(),
                retain_original=retain_original,
            )
        except (DocumentParseError, OSError) as exc:
            outcomes.append(FileOutcome(relative_path, "failed", error=str(exc)))
        else:
            outcomes.append(
                FileOutcome(relative_path, result.status, result.version_no)
            )
    return outcomes
