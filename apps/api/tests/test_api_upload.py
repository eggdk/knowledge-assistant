"""HTTP tests for the contract the teammate's page will call."""

import sqlite3
from io import BytesIO

import pytest
from docx import Document
from fastapi.testclient import TestClient
from openpyxl import Workbook
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

from app.api_routes import MAX_UPLOAD_BYTES
from app.cli import main as cli_main
from app.config import get_database_path
from app.knowledge_store import list_documents, rebuild_chunks
from app.main import app


@pytest.fixture
def client(tmp_path):
    database = tmp_path / "web-upload.sqlite3"
    app.dependency_overrides[get_database_path] = lambda: database
    try:
        with TestClient(app) as test_client:
            yield test_client, database
    finally:
        app.dependency_overrides.clear()


def create_base(client: TestClient) -> str:
    response = client.post("/api/knowledge-bases", json={"name": "  课程资料  "})
    assert response.status_code == 201
    assert response.json()["name"] == "课程资料"
    return response.json()["id"]


def word_bytes(text: str) -> bytes:
    document = Document()
    document.add_paragraph("巡检手册")
    document.add_table(rows=1, cols=1).cell(0, 0).text = text
    target = BytesIO()
    document.save(target)
    return target.getvalue()


def excel_bytes() -> bytes:
    workbook = Workbook()
    workbook.active.title = "库存"
    workbook.active.append(["配件", "数量"])
    workbook.active.append(["恒温阀门", 42])
    workbook.create_sheet("空表")
    target = BytesIO()
    workbook.save(target)
    return target.getvalue()


def pdf_bytes(*, with_text: bool = True, encrypted: bool = False) -> bytes:
    writer = PdfWriter()
    page = writer.add_blank_page(width=300, height=200)
    if with_text:
        names = NameObject
        page[names("/Resources")] = DictionaryObject({
            names("/Font"): DictionaryObject({
                names("/F1"): DictionaryObject({
                    names("/Type"): names("/Font"),
                    names("/Subtype"): names("/Type1"),
                    names("/BaseFont"): names("/Helvetica"),
                }),
            }),
        })
        stream = DecodedStreamObject()
        stream.set_data(b"BT /F1 12 Tf 15 100 Td (Orbital calibration checklist) Tj ET")
        page.replace_contents(stream)
    if encrypted:
        writer.encrypt("example-password")
    target = BytesIO()
    writer.write(target)
    return target.getvalue()


def test_new_formats_are_retrievable_after_http_upload_and_cli_import(client, tmp_path):
    http, database = client
    files = [
        ("manual.DOCX", word_bytes("巡检周期为十九天"), "巡检周期", "十九天"),
        ("inventory.xlsx", excel_bytes(), "恒温阀门", "恒温阀门\t42"),
        ("checklist.pdf", pdf_bytes(), "Orbital calibration", "Orbital calibration checklist"),
    ]
    upload_base = create_base(http)
    response = http.post(
        f"/api/knowledge-bases/{upload_base}/documents/import",
        files=[("files", (name, data)) for name, data, _, _ in files],
    )
    assert response.status_code == 200
    assert response.json()["failed"] == 0
    assert all(item["searchable"] and item["version_no"] == 1 for item in response.json()["files"])

    cli_base = create_base(http)
    source = tmp_path / "documents"
    source.mkdir()
    for name, data, _, _ in files:
        (source / name).write_bytes(data)
    assert cli_main(["--db", str(database), "import", "--kb", cli_base, "--dir", str(source)]) == 0
    assert rebuild_chunks(database, cli_base).documents == 3

    for kb_id in (upload_base, cli_base):
        for name, _, question, expected in files:
            result = http.post(f"/api/knowledge-bases/{kb_id}/questions", json={"question": question})
            assert result.status_code == 200
            match = result.json()["matches"][0]
            assert match["relative_path"] == name
            assert expected in match["content"]


def test_multiformat_batch_reports_failures_and_preserves_valid_versions(client):
    http, _ = client
    kb_id = create_base(http)
    url = f"/api/knowledge-bases/{kb_id}/documents/import"
    original = word_bytes("巡检周期为十九天")
    first = http.post(url, files={"files": ("manual.docx", original)})
    assert first.json()["files"][0]["status"] == "created"
    repeat = http.post(url, files={"files": ("manual.docx", original)})
    assert repeat.json()["files"][0]["status"] == "unchanged"

    mixed = http.post(url, files=[
        ("files", ("manual.docx", b"invalid zip")),
        ("files", ("scan.pdf", pdf_bytes(with_text=False))),
        ("files", ("locked.pdf", pdf_bytes(encrypted=True))),
        ("files", ("new.xlsx", excel_bytes())),
    ])
    assert mixed.status_code == 200
    assert mixed.json()["failed"] == 3
    broken, scan, encrypted, workbook = mixed.json()["files"]
    assert "Cannot parse" in broken["error"]
    assert "OCR" in scan["error"]
    assert "encrypted" in encrypted["error"]
    assert workbook["searchable"]
    listed = http.get(f"/api/knowledge-bases/{kb_id}/documents").json()
    assert [(item["relative_path"], item["version_no"]) for item in listed] == [
        ("manual.docx", 1), ("new.xlsx", 1),
    ]

    updated = http.post(url, files={"files": ("manual.docx", word_bytes("巡检周期为二十八天"))})
    assert updated.json()["files"][0]["status"] == "updated"
    assert updated.json()["files"][0]["version_no"] == 2
    result = http.post(f"/api/knowledge-bases/{kb_id}/questions", json={"question": "巡检周期"})
    assert "二十八天" in result.json()["matches"][0]["content"]


def test_upload_openapi_describes_file_picker_in_swagger(client) -> None:
    http, _ = client
    schema = http.get("/openapi.json").json()
    operation = schema["paths"]["/api/knowledge-bases/{kb_id}/documents/import"]["post"]
    body = operation["requestBody"]["content"]["multipart/form-data"]["schema"]
    component = schema["components"]["schemas"][body["$ref"].rsplit("/", 1)[-1]]

    assert component["properties"]["files"]["items"]["format"] == "binary"
    assert "relative_paths" in component["properties"]


def test_browser_form_upload_with_blank_optional_path_uses_filename(client) -> None:
    http, _ = client
    kb_id = create_base(http)
    response = http.post(
        f"/api/knowledge-bases/{kb_id}/documents/import",
        files={"files": ("intro.md", b"# Example", "text/markdown")},
        data={"relative_paths": ""},
    )

    assert response.status_code == 200
    assert response.json()["files"][0]["relative_path"] == "intro.md"
    assert response.json()["files"][0]["status"] == "created"


def test_create_list_upload_repeat_update_and_list_documents(client) -> None:
    http, database = client
    kb_id = create_base(http)
    assert http.get("/api/knowledge-bases").json() == [
        {"id": kb_id, "name": "课程资料"}
    ]

    url = f"/api/knowledge-bases/{kb_id}/documents/import"
    files = [
        ("files", ("intro.md", "# 中文".encode(), "text/markdown")),
        ("files", ("faq.txt", b"Question: A", "text/plain")),
    ]
    paths = {"relative_paths": ["manual/intro.md", "faq.txt"]}
    first = http.post(url, files=files, data=paths)
    assert first.status_code == 200
    assert [file["status"] for file in first.json()["files"]] == [
        "created", "created"
    ]
    assert first.json()["failed"] == 0
    assert all(file["searchable"] is True for file in first.json()["files"])

    repeated = http.post(url, files=files, data=paths)
    assert [file["status"] for file in repeated.json()["files"]] == [
        "unchanged", "unchanged"
    ]
    assert all(file["searchable"] is True for file in repeated.json()["files"])

    changed = http.post(
        url,
        files={"files": ("intro.md", "# 新版本".encode(), "text/markdown")},
        data={"relative_paths": "manual/intro.md"},
    )
    assert changed.json()["files"][0]["status"] == "updated"
    assert changed.json()["files"][0]["version_no"] == 2
    assert changed.json()["files"][0]["searchable"] is True

    listed = http.get(f"/api/knowledge-bases/{kb_id}/documents")
    assert listed.status_code == 200
    assert [(item["relative_path"], item["version_no"]) for item in listed.json()] == [
        ("faq.txt", 1), ("manual/intro.md", 2)
    ]
    assert all(item["searchable"] is True for item in listed.json())

    retrieved = http.post(
        f"/api/knowledge-bases/{kb_id}/questions", json={"question": "新版本"}
    )
    assert retrieved.status_code == 200
    matches = retrieved.json()["matches"]
    assert matches
    assert all(match["version_no"] == 2 for match in matches)

    with sqlite3.connect(database) as connection:
        copies = connection.execute(
            "SELECT original_bytes FROM document_versions ORDER BY imported_at"
        ).fetchall()
    assert "# 中文".encode() in [row[0] for row in copies]
    assert "# 新版本".encode() in [row[0] for row in copies]


def test_bad_file_is_reported_without_blocking_good_file(client) -> None:
    http, _ = client
    kb_id = create_base(http)
    response = http.post(
        f"/api/knowledge-bases/{kb_id}/documents/import",
        files=[
            ("files", ("bad.txt", b"\xff", "text/plain")),
            ("files", ("good.md", b"Good", "text/markdown")),
        ],
    )
    assert response.status_code == 200
    assert response.json()["failed"] == 1
    assert [item["status"] for item in response.json()["files"]] == [
        "failed", "created"
    ]
    assert "Cannot decode" in response.json()["files"][0]["error"]
    assert [item["searchable"] for item in response.json()["files"]] == [False, True]


def test_active_version_without_chunks_does_not_use_historical_chunks(client) -> None:
    http, database = client
    kb_id = create_base(http)
    url = f"/api/knowledge-bases/{kb_id}/documents/import"
    http.post(url, files={"files": ("guide.txt", "实验说明".encode(), "text/plain")})
    updated = http.post(url, files={"files": ("guide.txt", "新版实验说明".encode(), "text/plain")})
    assert updated.json()["files"][0]["version_no"] == 2
    # Simulate a legacy active version that has not had its chunks backfilled.
    with sqlite3.connect(database) as connection:
        connection.execute("DELETE FROM document_chunks WHERE version_no = 2")
    assert http.get(f"/api/knowledge-bases/{kb_id}/documents").json()[0]["searchable"] is False
    assert http.post(
        f"/api/knowledge-bases/{kb_id}/questions", json={"question": "实验"}
    ).json()["matches"] == []
    with sqlite3.connect(database) as connection:
        assert connection.execute("SELECT COUNT(*) FROM document_chunks").fetchone()[0] > 0


def test_old_chunk_strategy_is_not_ready_until_unchanged_import_backfills(client) -> None:
    http, database = client
    kb_id = create_base(http)
    url = f"/api/knowledge-bases/{kb_id}/documents/import"
    file = {"files": ("guide.txt", "实验说明".encode(), "text/plain")}
    http.post(url, files=file)
    with sqlite3.connect(database) as connection:
        connection.execute(
            "UPDATE document_chunks SET strategy_version = 'old-strategy', "
            "chunk_id = 'old_' || chunk_id"
        )
    assert http.get(f"/api/knowledge-bases/{kb_id}/documents").json()[0]["searchable"] is False
    repeated = http.post(url, files=file).json()["files"][0]
    assert (repeated["status"], repeated["version_no"], repeated["searchable"]) == (
        "unchanged", 1, True
    )
    assert http.get(f"/api/knowledge-bases/{kb_id}/documents").json()[0]["searchable"] is True


@pytest.mark.parametrize("bad_data", [b"\xff", b" \n\t"])
def test_failed_update_preserves_previous_searchable_version(client, bad_data) -> None:
    http, _ = client
    kb_id = create_base(http)
    url = f"/api/knowledge-bases/{kb_id}/documents/import"
    http.post(url, files={"files": ("guide.txt", "实验说明".encode(), "text/plain")})
    failed = http.post(url, files={"files": ("guide.txt", bad_data, "text/plain")})
    assert failed.json()["files"][0]["status"] == "failed"
    assert failed.json()["files"][0]["searchable"] is False
    record = http.get(f"/api/knowledge-bases/{kb_id}/documents").json()[0]
    assert (record["version_no"], record["searchable"]) == (1, True)


def test_delete_hides_document_from_listing_retrieval_and_rebuild(client) -> None:
    http, database = client
    kb_id = create_base(http)
    other_kb = create_base(http)
    base = f"/api/knowledge-bases/{kb_id}"
    upload = http.post(
        f"{base}/documents/import",
        files=[
            ("files", ("guide.txt", b"cedaronly", "text/plain")),
            ("files", ("keep.txt", b"amberonly", "text/plain")),
        ],
    )
    assert upload.json()["failed"] == 0
    document_id = http.get(f"{base}/documents").json()[0]["id"]
    question = {"question": "cedaronly"}
    assert http.post(f"{base}/questions", json=question).json()["matches"]

    assert http.delete(f"/api/knowledge-bases/{other_kb}/documents/{document_id}").status_code == 404
    assert http.delete(f"/api/knowledge-bases/missing/documents/{document_id}").status_code == 404
    assert http.delete(f"{base}/documents/missing").status_code == 404
    assert http.post(f"{base}/questions", json=question).json()["matches"]

    for _ in range(2):
        response = http.delete(f"{base}/documents/{document_id}")
        assert response.status_code == 204 and response.content == b""
    assert [item["relative_path"] for item in http.get(f"{base}/documents").json()] == ["keep.txt"]
    assert list_documents(database, kb_id) == [("keep.txt", 1)]
    assert rebuild_chunks(database, kb_id).documents == 1
    assert http.post(f"{base}/questions", json=question).json()["matches"] == []
    answer = http.post(f"{base}/answers", json=question).json()
    assert answer["answer_status"] == "insufficient_evidence" and answer["citations"] == []
    assert http.post(f"{base}/questions", json={"question": "amberonly"}).json()["matches"]
    with sqlite3.connect(database) as connection:
        assert connection.execute(
            "SELECT original_bytes FROM document_versions WHERE document_id = ?", (document_id,)
        ).fetchall() == [(b"cedaronly",)]
        assert connection.execute(
            "SELECT COUNT(*) FROM document_chunks WHERE document_id = ?", (document_id,)
        ).fetchone()[0] == 1


def test_reupload_restores_deleted_document_and_preserves_version_rules(client) -> None:
    http, database = client
    kb_id = create_base(http)
    base = f"/api/knowledge-bases/{kb_id}"

    def upload(data: bytes):
        result = http.post(
            f"{base}/documents/import",
            files={"files": ("guide.txt", data, "text/plain")},
            data={"relative_paths": "manual/guide.txt"},
        )
        assert result.status_code == 200
        return result.json()["files"][0]

    assert upload(b"firstversion")["version_no"] == 1
    assert upload(b"secondversion")["version_no"] == 2
    original = http.get(f"{base}/documents").json()[0]
    url = f"{base}/documents/{original['id']}"
    assert http.delete(url).status_code == 204
    assert upload(b"\xff")["status"] == "failed"
    assert http.get(f"{base}/documents").json() == []

    same = upload(b"secondversion")
    assert (same["status"], same["version_no"], same["searchable"]) == ("unchanged", 2, True)
    assert http.get(f"{base}/documents").json() == [original]
    assert http.post(f"{base}/questions", json={"question": "secondversion"}).json()["matches"]

    assert http.delete(url).status_code == 204
    changed = upload(b"thirdversion")
    assert (changed["status"], changed["version_no"], changed["searchable"]) == ("updated", 3, True)
    listed = http.get(f"{base}/documents").json()[0]
    assert (listed["id"], listed["version_no"]) == (original["id"], 3)
    assert http.post(f"{base}/questions", json={"question": "secondversion"}).json()["matches"] == []
    assert http.post(f"{base}/questions", json={"question": "thirdversion"}).json()["matches"]
    with sqlite3.connect(database) as connection:
        assert connection.execute(
            "SELECT version_no, original_bytes FROM document_versions ORDER BY version_no"
        ).fetchall() == [(1, b"firstversion"), (2, b"secondversion"), (3, b"thirdversion")]


def test_wrong_path_count_or_unsafe_path_is_rejected_before_writing(client) -> None:
    http, _ = client
    kb_id = create_base(http)
    url = f"/api/knowledge-bases/{kb_id}/documents/import"
    files = [("files", ("a.md", b"A", "text/markdown"))]

    wrong_count = http.post(
        url, files=files, data={"relative_paths": ["a.md", "b.md"]}
    )
    unsafe = http.post(url, files=files, data={"relative_paths": "../a.md"})

    assert wrong_count.status_code == 422
    assert unsafe.status_code == 422
    assert http.get(f"/api/knowledge-bases/{kb_id}/documents").json() == []


def test_oversized_upload_fails_without_storing_it(client) -> None:
    http, _ = client
    kb_id = create_base(http)
    response = http.post(
        f"/api/knowledge-bases/{kb_id}/documents/import",
        files={"files": ("large.txt", b"x" * (MAX_UPLOAD_BYTES + 1), "text/plain")},
    )
    assert response.status_code == 200
    assert response.json()["files"][0]["status"] == "failed"
    assert http.get(f"/api/knowledge-bases/{kb_id}/documents").json() == []


def test_unknown_knowledge_base_returns_404(client) -> None:
    http, _ = client
    assert http.get("/api/knowledge-bases/missing/documents").status_code == 404
    assert http.post(
        "/api/knowledge-bases/missing/documents/import",
        files={"files": ("a.md", b"A", "text/markdown")},
    ).status_code == 404


def test_unsupported_format_is_a_per_file_failure(client) -> None:
    http, _ = client
    kb_id = create_base(http)
    response = http.post(
        f"/api/knowledge-bases/{kb_id}/documents/import",
        files={"files": ("report.xls", b"unsupported", "application/octet-stream")},
    )
    assert response.status_code == 200
    assert response.json()["files"][0]["status"] == "failed"
    assert "Unsupported file type" in response.json()["files"][0]["error"]


def test_duplicate_paths_are_rejected_before_writing(client) -> None:
    http, _ = client
    kb_id = create_base(http)
    url = f"/api/knowledge-bases/{kb_id}/documents/import"
    response = http.post(
        url,
        files=[
            ("files", ("same.md", b"A", "text/markdown")),
            ("files", ("same.md", b"B", "text/markdown")),
        ],
    )
    assert response.status_code == 422
    assert http.get(f"/api/knowledge-bases/{kb_id}/documents").json() == []
