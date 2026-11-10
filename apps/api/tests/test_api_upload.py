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
