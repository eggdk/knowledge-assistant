"""HTTP contract for the teammate's first knowledge-base management page."""

from pathlib import Path
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field

from app.config import get_database_path
from app.knowledge_store import (
    create_knowledge_base,
    import_document,
    knowledge_base_exists,
    list_document_records,
    list_knowledge_bases,
    validate_relative_path,
)
from app.text_parser import DocumentParseError


router = APIRouter(prefix="/api/knowledge-bases", tags=["knowledge bases"])

MAX_UPLOAD_BYTES = 5 * 1024 * 1024
MAX_FILES_PER_REQUEST = 20


class CreateKnowledgeBaseRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)


class KnowledgeBaseView(BaseModel):
    id: str
    name: str


class DocumentView(BaseModel):
    id: str
    relative_path: str
    version_no: int
    sha256: str
    imported_at: str
    searchable: bool = False


class FileUploadResult(BaseModel):
    relative_path: str
    status: Literal["created", "updated", "unchanged", "failed"]
    version_no: int | None = None
    error: str | None = None
    searchable: bool = False


class BatchUploadResponse(BaseModel):
    files: list[FileUploadResult]
    failed: int


def _require_knowledge_base(database_path: Path, kb_id: str) -> None:
    if not knowledge_base_exists(database_path, kb_id):
        raise HTTPException(status_code=404, detail="Knowledge base not found")


@router.post("", response_model=KnowledgeBaseView, status_code=201)
def create_base(
    request: CreateKnowledgeBaseRequest,
    database_path: Annotated[Path, Depends(get_database_path)],
) -> KnowledgeBaseView:
    name = request.name.strip()
    if not name:
        raise HTTPException(status_code=422, detail="Knowledge-base name is empty")
    kb_id = create_knowledge_base(database_path, name)
    return KnowledgeBaseView(id=kb_id, name=name)


@router.get("", response_model=list[KnowledgeBaseView])
def get_bases(
    database_path: Annotated[Path, Depends(get_database_path)],
) -> list[KnowledgeBaseView]:
    return [
        KnowledgeBaseView(id=kb_id, name=name)
        for kb_id, name in list_knowledge_bases(database_path)
    ]


@router.get("/{kb_id}/documents", response_model=list[DocumentView])
def get_documents(
    kb_id: str,
    database_path: Annotated[Path, Depends(get_database_path)],
) -> list[DocumentView]:
    _require_knowledge_base(database_path, kb_id)
    return [
        DocumentView(
            id=record.document_id,
            relative_path=record.relative_path,
            version_no=record.version_no,
            sha256=record.sha256,
            imported_at=record.imported_at,
        )
        for record in list_document_records(database_path, kb_id)
    ]


@router.post("/{kb_id}/documents/import", response_model=BatchUploadResponse)
def upload_documents(
    kb_id: str,
    files: Annotated[list[UploadFile], File(description="MD/TXT files to import")],
    database_path: Annotated[Path, Depends(get_database_path)],
    relative_paths: Annotated[list[str] | None, Form()] = None,
) -> BatchUploadResponse:
    """Upload selected files; each parse failure is reported independently."""
    _require_knowledge_base(database_path, kb_id)
    if len(files) > MAX_FILES_PER_REQUEST:
        raise HTTPException(status_code=422, detail="Too many files in one request")
    if relative_paths is not None and len(relative_paths) != len(files):
        raise HTTPException(
            status_code=422, detail="relative_paths must match files one-to-one"
        )

    paths = (
        relative_paths
        if relative_paths is not None
        else [upload.filename or "" for upload in files]
    )
    if len(paths) != len(set(paths)):
        raise HTTPException(status_code=422, detail="Duplicate relative path")

    # Validate the entire batch before writing its first file.
    for upload, relative_path in zip(files, paths, strict=True):
        filename = upload.filename or ""
        try:
            validate_relative_path(relative_path)
            validate_relative_path(filename)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        if "/" in filename:
            raise HTTPException(
                status_code=422, detail="File name must not contain directories"
            )
        if relative_path.rsplit("/", 1)[-1] != filename:
            raise HTTPException(
                status_code=422, detail="Relative path must end with the file name"
            )

    outcomes: list[FileUploadResult] = []
    for upload, relative_path in zip(files, paths, strict=True):
        try:
            data = upload.file.read(MAX_UPLOAD_BYTES + 1)
        except OSError as exc:
            outcomes.append(
                FileUploadResult(
                    relative_path=relative_path,
                    status="failed",
                    error=f"Cannot read uploaded file: {exc}",
                )
            )
            continue
        if len(data) > MAX_UPLOAD_BYTES:
            outcomes.append(
                FileUploadResult(
                    relative_path=relative_path,
                    status="failed",
                    error=f"File exceeds {MAX_UPLOAD_BYTES} bytes",
                )
            )
            continue

        try:
            result = import_document(
                database_path, kb_id, relative_path, data, retain_original=True
            )
        except DocumentParseError as exc:
            outcomes.append(
                FileUploadResult(
                    relative_path=relative_path, status="failed", error=str(exc)
                )
            )
        else:
            outcomes.append(
                FileUploadResult(
                    relative_path=relative_path,
                    status=result.status,
                    version_no=result.version_no,
                )
            )

    return BatchUploadResponse(
        files=outcomes,
        failed=sum(outcome.status == "failed" for outcome in outcomes),
    )
