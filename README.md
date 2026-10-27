# Knowledge Assistant

BUAA course project: an embeddable knowledge-base Q&A assistant.

This repository now has a **local MD/TXT import and browser-upload API
foundation**. It can create a knowledge base, import selected local files or
uploaded files, track changed versions, prepare traceable MD/TXT chunks, and
try a CLI-only keyword retrieval baseline. It does not yet provide an end-user
search API, answer questions, cite sources, provide a web page, or integrate
with Agent Insight.

## Backend setup (Windows PowerShell)

Use Python 3.12. From the repository root:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r apps/api/requirements.txt
Set-Location apps/api
& ..\..\.venv\Scripts\python.exe -m pytest
& ..\..\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Open <http://127.0.0.1:8000/health> to check the API, or
<http://127.0.0.1:8000/docs> to see FastAPI's interactive API documentation.
Use `Ctrl+C` to stop the server.

The `/docs` page now lets you create a knowledge base and upload MD/TXT files
without a separate frontend. See [Backend lesson 03](docs/learning/03-web-upload-api.md)
for a guided walkthrough and the [A/B API handoff](docs/api/knowledge-base-v1.md)
for exact requests and responses. An uploaded document is **stored but not yet
searchable**; the API returns `searchable: false` until indexing is built.

## Local MD/TXT import

From `apps/api`, create a knowledge base and copy its printed `kb_...` ID:

```powershell
& ..\..\.venv\Scripts\python.exe -m app.cli kb create --name "Course demo"
& ..\..\.venv\Scripts\python.exe -m app.cli kb list
& ..\..\.venv\Scripts\python.exe -m app.cli import --kb YOUR_KB_ID --dir ..\..\examples\sample_docs
& ..\..\.venv\Scripts\python.exe -m app.cli docs list --kb YOUR_KB_ID
& ..\..\.venv\Scripts\python.exe -m app.cli chunks list --kb YOUR_KB_ID
& ..\..\.venv\Scripts\python.exe -m app.cli search --kb YOUR_KB_ID --query "自动回答问题"
```

The team chose to keep original files by default: exact source bytes are saved
inside the local SQLite database alongside parsed text and source path. An
explicit `--originals skip` is available for a special import where no original
copy is wanted. Runtime data is saved in ignored `storage/`; do not commit
private documents or the database.

The `.venv/` directory is local to each developer and must not be committed.
SQLite is used for knowledge bases, documents, and active document versions.
Missing files from a later partial import are never deleted automatically.

## Project decisions

See [the first backend decision record](docs/decisions/0001-backend-foundation.md)
for confirmed choices and remaining questions.
See [the import decision record](docs/decisions/0002-local-import.md)
for file identity, versioning, and original-copy policy.
For a plain-language walkthrough of the first request and tests, read
[Backend lesson 01](docs/learning/01-backend-foundation.md).
For the import flow and commands, read
[Backend lesson 02](docs/learning/02-local-import.md).
For the next search-preparation step, read
[Backend lesson 04](docs/learning/04-text-chunks.md) and
[chunking decision 0004](docs/decisions/0004-mdtxt-chunking.md).
For the first CLI-only retrieval baseline, read
[Backend lesson 05](docs/learning/05-keyword-search.md) and
[retrieval decision 0005](docs/decisions/0005-keyword-baseline.md).
To measure its actual misses and false matches on a small, fictional dataset,
run `python -m app.evaluation` from `apps/api` and read
[Backend lesson 06](docs/learning/06-retrieval-evaluation.md). The demo labels
are separate from the imported documents; the results are not a course-quality
claim or evidence that end-user answering is ready.
For a first run on pinned public Agent Insight user-guide documents, run
`python -m app.evaluation --dataset ../../evals/agent_insight` from `apps/api`.
Read [Backend lesson 07](docs/learning/07-agent-insight-real-docs.md) and
[the source manifest](evals/agent_insight/SOURCE.md) for provenance, scores,
and the important limitation that the course task did not specify a particular
Agent Insight repository version.
