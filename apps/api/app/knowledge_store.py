"""Small SQLite store shared by CLI imports and later HTTP uploads.

This stage stores parsed text and versions, but deliberately does not create a
search index or answer questions yet.
"""

import hashlib
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator
from uuid import uuid4

from app.chunking import CHUNK_STRATEGY_VERSION, TextChunk, split_text_into_chunks
from app.text_parser import parse_text_bytes


SCHEMA = """
PRAGMA foreign_keys = ON;
CREATE TABLE IF NOT EXISTS knowledge_bases (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS documents (
    id TEXT PRIMARY KEY,
    kb_id TEXT NOT NULL REFERENCES knowledge_bases(id),
    source_path TEXT NOT NULL,
    active_version_no INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(kb_id, source_path)
);
CREATE TABLE IF NOT EXISTS document_versions (
    document_id TEXT NOT NULL REFERENCES documents(id),
    version_no INTEGER NOT NULL,
    sha256 TEXT NOT NULL,
    content TEXT NOT NULL,
    original_bytes BLOB,
    imported_at TEXT NOT NULL,
    PRIMARY KEY(document_id, version_no)
);
CREATE TABLE IF NOT EXISTS document_chunks (
    chunk_id TEXT PRIMARY KEY,
    kb_id TEXT NOT NULL REFERENCES knowledge_bases(id),
    document_id TEXT NOT NULL,
    version_no INTEGER NOT NULL,
    strategy_version TEXT NOT NULL,
    chunk_no INTEGER NOT NULL,
    content TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    heading TEXT NOT NULL,
    start_offset INTEGER NOT NULL,
    end_offset INTEGER NOT NULL,
    start_line INTEGER NOT NULL,
    end_line INTEGER NOT NULL,
    FOREIGN KEY(document_id, version_no)
        REFERENCES document_versions(document_id, version_no),
    UNIQUE(document_id, version_no, strategy_version, chunk_no)
);
CREATE INDEX IF NOT EXISTS idx_chunks_kb_version
    ON document_chunks(kb_id, document_id, version_no, strategy_version);
"""


@dataclass(frozen=True)
class ImportResult:
    relative_path: str
    status: str
    version_no: int


@dataclass(frozen=True)
class DocumentRecord:
    document_id: str
    relative_path: str
    version_no: int
    sha256: str
    imported_at: str


@dataclass(frozen=True)
class StoredChunk:
    chunk_id: str
    kb_id: str
    document_id: str
    relative_path: str
    version_no: int
    chunk_no: int
    content: str
    content_hash: str
    heading: str
    start_offset: int
    end_offset: int
    start_line: int
    end_line: int


@contextmanager
def _connect(database_path: Path) -> Iterator[sqlite3.Connection]:
    database_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(database_path)
    try:
        connection.execute("PRAGMA foreign_keys = ON")
        connection.executescript(SCHEMA)
        with connection:
            yield connection
    finally:
        connection.close()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def create_knowledge_base(database_path: Path, name: str) -> str:
    if not name.strip():
        raise ValueError("Knowledge-base name must not be empty")

    kb_id = "kb_" + uuid4().hex
    with _connect(database_path) as connection:
        connection.execute(
            "INSERT INTO knowledge_bases (id, name, created_at) VALUES (?, ?, ?)",
            (kb_id, name.strip(), _now()),
        )
    return kb_id


def list_knowledge_bases(database_path: Path) -> list[tuple[str, str]]:
    with _connect(database_path) as connection:
        return connection.execute(
            "SELECT id, name FROM knowledge_bases ORDER BY created_at, id"
        ).fetchall()


def knowledge_base_exists(database_path: Path, kb_id: str) -> bool:
    with _connect(database_path) as connection:
        return connection.execute(
            "SELECT 1 FROM knowledge_bases WHERE id = ?", (kb_id,)
        ).fetchone() is not None


def validate_relative_path(relative_path: str) -> None:
    """Reject absolute paths and path traversal before any import is written."""
    if (
        not relative_path
        or "\\" in relative_path
        or relative_path.startswith("/")
        or ":" in relative_path
        or "\x00" in relative_path
        or any(part in {"", ".", ".."} for part in relative_path.split("/"))
    ):
        raise ValueError("Document path must be a safe relative POSIX path")


def _insert_chunks(
    connection: sqlite3.Connection,
    kb_id: str,
    document_id: str,
    version_no: int,
    chunks: list[TextChunk],
) -> None:
    rows = []
    for chunk in chunks:
        identity = f"{document_id}:{version_no}:{CHUNK_STRATEGY_VERSION}:{chunk.ordinal}"
        chunk_id = "chk_" + hashlib.sha256(identity.encode("utf-8")).hexdigest()[:32]
        rows.append(
            (
                chunk_id,
                kb_id,
                document_id,
                version_no,
                CHUNK_STRATEGY_VERSION,
                chunk.ordinal,
                chunk.text,
                hashlib.sha256(chunk.text.encode("utf-8")).hexdigest(),
                chunk.heading,
                chunk.start_offset,
                chunk.end_offset,
                chunk.start_line,
                chunk.end_line,
            )
        )
    connection.executemany(
        """INSERT INTO document_chunks
           (chunk_id, kb_id, document_id, version_no, strategy_version, chunk_no,
            content, content_hash, heading, start_offset, end_offset,
            start_line, end_line)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        rows,
    )


def import_document(
    database_path: Path,
    kb_id: str,
    relative_path: str,
    data: bytes,
    *,
    retain_original: bool,
) -> ImportResult:
    """Import one selected file; only a successful parse changes active data."""
    validate_relative_path(relative_path)

    content = parse_text_bytes(relative_path.rsplit("/", 1)[-1], data)
    digest = hashlib.sha256(data).hexdigest()
    chunks = split_text_into_chunks(content, Path(relative_path).suffix)

    with _connect(database_path) as connection:
        connection.execute("BEGIN IMMEDIATE")
        if connection.execute(
            "SELECT 1 FROM knowledge_bases WHERE id = ?", (kb_id,)
        ).fetchone() is None:
            raise ValueError(f"Unknown knowledge base: {kb_id}")

        existing = connection.execute(
            """SELECT d.id, d.active_version_no, v.sha256
               FROM documents AS d
               JOIN document_versions AS v
                 ON v.document_id = d.id AND v.version_no = d.active_version_no
               WHERE d.kb_id = ? AND d.source_path = ?""",
            (kb_id, relative_path),
        ).fetchone()

        if existing is not None and existing[2] == digest:
            has_chunks = connection.execute(
                """SELECT 1 FROM document_chunks
                   WHERE document_id = ? AND version_no = ?
                     AND strategy_version = ? LIMIT 1""",
                (existing[0], existing[1], CHUNK_STRATEGY_VERSION),
            ).fetchone()
            if has_chunks is None:
                _insert_chunks(connection, kb_id, existing[0], existing[1], chunks)
            if retain_original:
                connection.execute(
                    """UPDATE document_versions SET original_bytes = ?
                       WHERE document_id = ? AND version_no = ?
                         AND original_bytes IS NULL""",
                    (data, existing[0], existing[1]),
                )
            return ImportResult(relative_path, "unchanged", existing[1])

        if existing is None:
            document_id = "doc_" + uuid4().hex
            version_no = 1
            connection.execute(
                """INSERT INTO documents
                   (id, kb_id, source_path, active_version_no, created_at)
                   VALUES (?, ?, ?, ?, ?)""",
                (document_id, kb_id, relative_path, version_no, _now()),
            )
            status = "created"
        else:
            document_id = existing[0]
            version_no = existing[1] + 1
            status = "updated"

        connection.execute(
            """INSERT INTO document_versions
               (document_id, version_no, sha256, content, original_bytes, imported_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                document_id,
                version_no,
                digest,
                content,
                data if retain_original else None,
                _now(),
            ),
        )
        _insert_chunks(connection, kb_id, document_id, version_no, chunks)
        if existing is not None:
            connection.execute(
                "UPDATE documents SET active_version_no = ? WHERE id = ?",
                (version_no, document_id),
            )

    return ImportResult(relative_path, status, version_no)


def list_documents(database_path: Path, kb_id: str) -> list[tuple[str, int]]:
    with _connect(database_path) as connection:
        return connection.execute(
            """SELECT source_path, active_version_no FROM documents
               WHERE kb_id = ? ORDER BY source_path""",
            (kb_id,),
        ).fetchall()


def list_document_records(database_path: Path, kb_id: str) -> list[DocumentRecord]:
    with _connect(database_path) as connection:
        rows = connection.execute(
            """SELECT d.id, d.source_path, d.active_version_no,
                      v.sha256, v.imported_at
               FROM documents AS d
               JOIN document_versions AS v
                 ON v.document_id = d.id AND v.version_no = d.active_version_no
               WHERE d.kb_id = ? ORDER BY d.source_path""",
            (kb_id,),
        ).fetchall()
    return [DocumentRecord(*row) for row in rows]


def list_active_chunks(database_path: Path, kb_id: str) -> list[StoredChunk]:
    """Return only chunks for each document's active version and current strategy."""
    with _connect(database_path) as connection:
        rows = connection.execute(
            """SELECT c.chunk_id, c.kb_id, c.document_id, d.source_path,
                      c.version_no, c.chunk_no, c.content, c.content_hash,
                      c.heading, c.start_offset, c.end_offset,
                      c.start_line, c.end_line
               FROM document_chunks AS c
               JOIN documents AS d ON d.id = c.document_id
               WHERE d.kb_id = ? AND c.kb_id = d.kb_id
                 AND c.version_no = d.active_version_no
                 AND c.strategy_version = ?
               ORDER BY d.source_path, c.chunk_no""",
            (kb_id, CHUNK_STRATEGY_VERSION),
        ).fetchall()
    return [StoredChunk(*row) for row in rows]
