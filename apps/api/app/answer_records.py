"""Keep final answer snapshots and local feedback for knowledge-base maintenance."""

import json
from pathlib import Path
from uuid import uuid4

from app.knowledge_store import _connect, _now


def save_answer(database_path: Path, kb_id: str, question: str, history: list[str], response: dict) -> str:
    answer_id = "ans_" + uuid4().hex
    with _connect(database_path) as connection:
        connection.execute(
            """INSERT INTO answer_records
               (id, kb_id, question, history_json, response_json, answer_status, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (answer_id, kb_id, question, json.dumps(history, ensure_ascii=False),
             json.dumps(response, ensure_ascii=False), response["answer_status"], _now()),
        )
    return answer_id


def set_feedback(database_path: Path, kb_id: str, answer_id: str, rating: str, comment: str) -> bool:
    with _connect(database_path) as connection:
        connection.execute("BEGIN IMMEDIATE")
        if connection.execute(
            "SELECT 1 FROM answer_records WHERE kb_id = ? AND id = ?", (kb_id, answer_id),
        ).fetchone() is None:
            return False
        connection.execute(
            """INSERT INTO answer_feedback (answer_id, rating, comment, updated_at)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(answer_id) DO UPDATE SET
                 rating = excluded.rating, comment = excluded.comment, updated_at = excluded.updated_at""",
            (answer_id, rating, comment, _now()),
        )
    return True


def list_answer_records(database_path: Path, kb_id: str, *, needs_review: bool, limit: int, offset: int) -> list[dict]:
    with _connect(database_path) as connection:
        rows = connection.execute(
            """SELECT a.id, a.question, a.history_json, a.response_json, a.created_at,
                      f.rating, f.comment, f.updated_at
               FROM answer_records AS a
               LEFT JOIN answer_feedback AS f ON f.answer_id = a.id
               WHERE a.kb_id = ?
                 AND (? = 0 OR a.answer_status = 'insufficient_evidence' OR f.rating = 'unhelpful')
               ORDER BY a.created_at DESC, a.id DESC LIMIT ? OFFSET ?""",
            (kb_id, needs_review, limit, offset),
        ).fetchall()
    return [
        {"answer_id": row[0], "question": row[1], "history": json.loads(row[2]),
         "response": {**json.loads(row[3]), "answer_id": row[0]}, "created_at": row[4],
         "rating": row[5], "comment": row[6], "feedback_updated_at": row[7]}
        for row in rows
    ]
