"""Small, real tests for the backend foundation."""

import sqlite3

from fastapi.testclient import TestClient

from app.main import app


def test_health_returns_ok() -> None:
    with TestClient(app) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_sqlite_can_store_and_read_chinese_text(tmp_path) -> None:
    """Check the selected local database without fixing a schema prematurely."""
    database_path = tmp_path / "smoke.sqlite3"

    with sqlite3.connect(database_path) as connection:
        connection.execute("CREATE TABLE smoke (content TEXT NOT NULL)")
        connection.execute(
            "INSERT INTO smoke (content) VALUES (?)", ("中文测试资料",)
        )
        stored = connection.execute("SELECT content FROM smoke").fetchone()

    assert stored == ("中文测试资料",)
