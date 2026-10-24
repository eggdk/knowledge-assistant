# Decision 0001: backend foundation

Status: confirmed by the A-role student on 2026-10-21. This is a team
implementation choice, **not** a technology requirement from the course.

## Chosen for the first version

- Python 3.12 as the backend language (A's current machine has 3.12.4).
- FastAPI for HTTP endpoints, SQLite for local application data.
- pytest plus FastAPI's TestClient for backend tests.
- Keep backend source in `apps/api/`; the teammate can add the web client in
  `apps/web/` without sharing Python source files.

The first increment contains only a `/health` endpoint and a SQLite smoke
test. The smoke test uses a temporary database, so it does not establish the
production database schema or create runtime data in the repository.

## Still to decide together

- File identity and the first version/update model are now recorded in
  [decision 0002](0002-local-import.md); later retrieval metadata is still open.
- Which Word/Excel/PDF variants the teacher expects, and whether scanning a
  backend-local directory is required in addition to browser-selected uploads.
- Model/embedding provider, credentials, budget, and test-data restrictions.
- Teacher-designated Agent Insight repository and compatible runtime version.

Do not present this foundation as a completed knowledge-base or Q&A service.
