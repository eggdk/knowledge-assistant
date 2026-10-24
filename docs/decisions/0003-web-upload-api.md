# Decision 0003: first browser-upload API

Status: implemented as a provisional A/B interface on 2026-10-21; B should review field names and local frontend integration before relying on them broadly.

- The HTTP side exposes create/list knowledge bases, list documents, and batch MD/TXT upload. It reuses the same `import_document()` function as the CLI.
- Browser file/folder selection is transmitted as multipart `files` plus optional positionally matched `relative_paths`. The backend validates all paths before the first write.
- Exact original bytes are retained, matching [decision 0002](0002-local-import.md).
- A bad file yields a per-file failure while valid siblings succeed; malformed batch structure yields HTTP 422 with no writes.
- The initial upload is synchronous and limited to 20 files of 5 MiB each. These are implementation safeguards for a small local stage, not course-imposed limits.
- Responses explicitly say `searchable: false` until indexing exists. No job-progress claim, retrieval claim, or public deployment claim is made.
- No broad CORS rule or authentication is added without knowing the B-side development origin/deployment plan. The UI can use a same-origin development proxy in the meantime.

See [the A/B API handoff](../api/knowledge-base-v1.md) for exact routes and payloads.
