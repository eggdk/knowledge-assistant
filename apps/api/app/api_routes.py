"""HTTP contract for the teammate's first knowledge-base management page."""

import logging
import re
from pathlib import Path
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile
from pydantic import BaseModel, Field, StringConstraints

from app.answer_generation import (
    MODEL_NAME,
    ModelAnswerError,
    ModelNotConfigured,
    generate_answer,
)
from app.config import get_database_path
from app.knowledge_store import (
    create_knowledge_base,
    delete_document,
    import_document,
    knowledge_base_exists,
    list_document_records,
    list_knowledge_bases,
    validate_relative_path,
)
from app.retrieval import SearchHit, search_knowledge_base
from app.text_parser import DocumentParseError


router = APIRouter(prefix="/api/knowledge-bases", tags=["knowledge bases"])
logger = logging.getLogger("uvicorn.error")

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
    searchable: bool = Field(
        description="当前文档版本有当前策略的文本块可参与检索；不代表模型已配置或答案一定正确"
    )


class FileUploadResult(BaseModel):
    relative_path: str
    status: Literal["created", "updated", "unchanged", "failed"]
    version_no: int | None = None
    error: str | None = None
    searchable: bool = Field(
        default=False,
        description="本次成功导入后是否有文本块；失败为 false，旧文档状态请查询文档列表",
    )


class BatchUploadResponse(BaseModel):
    files: list[FileUploadResult]
    failed: int


HistoryQuestion = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=1000)]
_FOLLOW_UP = re.compile(r"刚才|前面提到|上面提到|上述|它|这个|那个|这种|那种|这两种|前者|后者|^那[，、 ]")


class QuestionWithHistory(BaseModel):
    question: str = Field(min_length=1, max_length=1000)
    history: list[HistoryQuestion] = Field(default_factory=list, max_length=3)


class AskQuestionRequest(QuestionWithHistory):
    limit: int = Field(default=5, ge=1, le=20)


class SourceMatchView(BaseModel):
    chunk_id: str
    relative_path: str
    version_no: int
    start_line: int
    end_line: int
    heading: str
    content: str
    score: float


class AskQuestionResponse(BaseModel):
    question: str
    answer: str | None = None
    answer_status: Literal["not_generated"] = "not_generated"
    matches: list[SourceMatchView]


class GenerateAnswerRequest(QuestionWithHistory):
    limit: int = Field(default=5, ge=1, le=8)


class CitationView(SourceMatchView):
    label: str


class GenerateAnswerResponse(BaseModel):
    question: str
    answer: str
    answer_status: Literal["generated", "insufficient_evidence"]
    model: str | None
    citations: list[CitationView]


def _require_knowledge_base(database_path: Path, kb_id: str) -> None:
    if not knowledge_base_exists(database_path, kb_id):
        raise HTTPException(status_code=404, detail="Knowledge base not found")


def _resolve_follow_up(question: str, history: list[str]) -> tuple[str, list[str]]:
    if not history or not _FOLLOW_UP.search(question):
        return question, []
    # A recent independent question begins a new topic.
    start = next(
        (i for i in range(len(history) - 1, -1, -1) if not _FOLLOW_UP.search(history[i])),
        0,
    )
    context = history[start:]
    return "\n".join([*context, question]), context


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
            searchable=record.searchable,
        )
        for record in list_document_records(database_path, kb_id)
    ]


@router.delete("/{kb_id}/documents/{document_id}", status_code=204, response_class=Response)
def remove_document(
    kb_id: str,
    document_id: str,
    database_path: Annotated[Path, Depends(get_database_path)],
) -> Response:
    """Remove a document from the list and retrieval, preserving its history."""
    _require_knowledge_base(database_path, kb_id)
    if not delete_document(database_path, kb_id, document_id):
        raise HTTPException(status_code=404, detail="Document not found in this knowledge base")
    return Response(status_code=204)


@router.post("/{kb_id}/questions", response_model=AskQuestionResponse)
def ask_question(
    kb_id: str,
    request: AskQuestionRequest,
    database_path: Annotated[Path, Depends(get_database_path)],
) -> AskQuestionResponse:
    """Accept a question and return candidate source passages, not an answer."""
    _require_knowledge_base(database_path, kb_id)
    question = request.question.strip()
    if not question:
        raise HTTPException(status_code=422, detail="Question must not be blank")

    query, _ = _resolve_follow_up(question, request.history)
    hits = search_knowledge_base(database_path, kb_id, query, limit=request.limit)
    logger.info("retrieval kb=%s matches=%d", kb_id, len(hits))
    return AskQuestionResponse(
        question=question,
        matches=[_source_match(hit) for hit in hits],
    )


def _source_match(hit: SearchHit) -> SourceMatchView:
    return SourceMatchView(
        chunk_id=hit.chunk.chunk_id,
        relative_path=hit.chunk.relative_path,
        version_no=hit.chunk.version_no,
        start_line=hit.chunk.start_line,
        end_line=hit.chunk.end_line,
        heading=hit.chunk.heading,
        content=hit.chunk.content,
        score=hit.score,
    )


@router.post("/{kb_id}/answers", response_model=GenerateAnswerResponse)
def answer_question(
    kb_id: str,
    request: GenerateAnswerRequest,
    database_path: Annotated[Path, Depends(get_database_path)],
) -> GenerateAnswerResponse:
    """Retrieve current evidence, using recent questions to resolve follow-ups."""
    _require_knowledge_base(database_path, kb_id)
    question = request.question.strip()
    if not question:
        raise HTTPException(status_code=422, detail="Question must not be blank")

    query, context = _resolve_follow_up(question, request.history)
    hits = search_knowledge_base(database_path, kb_id, query, limit=request.limit)
    try:
        result = generate_answer(question, hits, history=context)
    except ModelNotConfigured as exc:
        logger.warning("answer kb=%s matches=%d model_key=missing", kb_id, len(hits))
        raise HTTPException(status_code=503, detail="Model API key is not configured") from exc
    except ModelAnswerError as exc:
        logger.warning("answer kb=%s matches=%d model_result=invalid", kb_id, len(hits))
        raise HTTPException(status_code=502, detail="Model could not produce a valid answer") from exc

    logger.info(
        "answer kb=%s matches=%d status=%s citations=%d",
        kb_id,
        len(hits),
        result.status,
        len(result.citation_ids),
    )

    return GenerateAnswerResponse(
        question=question,
        answer=result.answer,
        answer_status=result.status,
        model=MODEL_NAME if hits else None,
        citations=[
            CitationView(label=label, **_source_match(hit).model_dump())
            for label, hit in zip(result.citation_ids, result.cited_hits, strict=True)
        ],
    )


@router.post("/{kb_id}/documents/import", response_model=BatchUploadResponse)
def upload_documents(
    kb_id: str,
    files: Annotated[
        list[UploadFile],
        File(
            description=(
                "点击“选择文件”选取本机的 .md 或 .txt 文件；"
                "不要在文本框中粘贴文件路径。需要多选时点击 Add string item。"
            ),
            json_schema_extra={"items": {"type": "string", "format": "binary"}},
        ),
    ],
    database_path: Annotated[Path, Depends(get_database_path)],
    relative_paths: Annotated[
        list[str] | None,
        Form(description="普通文件上传请留空；仅需保留文件夹层级时才逐个填写相对路径。"),
    ] = None,
) -> BatchUploadResponse:
    """从浏览器上传文件内容到知识库。先填 kb_id，再选文件并点 Execute。"""
    _require_knowledge_base(database_path, kb_id)
    # Swagger sends one empty form field when its optional path box is left blank.
    if relative_paths == [""]:
        relative_paths = None
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
                    searchable=result.searchable,
                )
            )

    return BatchUploadResponse(
        files=outcomes,
        failed=sum(outcome.status == "failed" for outcome in outcomes),
    )
