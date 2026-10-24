"""HTTP tests for the contract the teammate's page will call."""

import sqlite3

import pytest
from fastapi.testclient import TestClient

from app.api_routes import MAX_UPLOAD_BYTES
from app.config import get_database_path
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
    assert all(file["searchable"] is False for file in first.json()["files"])

    repeated = http.post(url, files=files, data=paths)
    assert [file["status"] for file in repeated.json()["files"]] == [
        "unchanged", "unchanged"
    ]

    changed = http.post(
        url,
        files={"files": ("intro.md", "# 新版本".encode(), "text/markdown")},
        data={"relative_paths": "manual/intro.md"},
    )
    assert changed.json()["files"][0]["status"] == "updated"
    assert changed.json()["files"][0]["version_no"] == 2

    listed = http.get(f"/api/knowledge-bases/{kb_id}/documents")
    assert listed.status_code == 200
    assert [(item["relative_path"], item["version_no"]) for item in listed.json()] == [
        ("faq.txt", 1), ("manual/intro.md", 2)
    ]
    assert all(item["searchable"] is False for item in listed.json())

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
        files={"files": ("report.pdf", b"%PDF", "application/pdf")},
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
