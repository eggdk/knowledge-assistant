# Knowledge-base HTTP API v1 — A/B handoff

Status: implemented for local development on 2026-10-21. B should review this provisional contract before wiring the file-management UI. This page describes the **storage/import** stage. The separate [question API v1](question-retrieval-v1.md) accepts a question and returns candidate source passages, without a generated answer.

Base URL when running locally: `http://127.0.0.1:8000`. Interactive API page: `/docs`.

| Action | Method and path | Request | Response |
|---|---|---|---|
| Create a knowledge base | `POST /api/knowledge-bases` | JSON `{"name":"课程资料"}` | `201`, `{"id":"kb_...","name":"课程资料"}` |
| List knowledge bases | `GET /api/knowledge-bases` | None | Array of `{id,name}` |
| List imported documents | `GET /api/knowledge-bases/{kb_id}/documents` | None | Array of `{id,relative_path,version_no,sha256,imported_at,searchable}` |
| Upload selected files | `POST /api/knowledge-bases/{kb_id}/documents/import` | `multipart/form-data` | `{files:[...],failed:N}` |

For upload, append every selected file under the repeated form field `files`. Optionally append one `relative_paths` field per file, in the **same order**, to retain a browser-selected folder's structure. For ordinary multi-file selection, omit `relative_paths`; each file's name becomes its path. A relative path must be safe and end with the file's exact name, for example `manual/intro.md` for `intro.md`. Paths in one request must be unique.

Browser-side example (framework-neutral):

```javascript
const form = new FormData();
for (const file of selectedFiles) {
  form.append("files", file);
  form.append("relative_paths", file.webkitRelativePath || file.name);
}
const response = await fetch(`/api/knowledge-bases/${kbId}/documents/import`, {
  method: "POST",
  body: form,
});
const result = await response.json();
```

Do **not** set the `Content-Type` header manually for `FormData`; the browser supplies the multipart boundary. The relative URL assumes the frontend uses the same origin or a development proxy to the backend. Cross-origin access is not enabled by default; agree on the frontend dev address before adding a narrow CORS rule.

Example successful/partial response:

```json
{
  "files": [
    {"relative_path":"manual/intro.md","status":"created","version_no":1,"error":null,"searchable":false},
    {"relative_path":"broken.txt","status":"failed","version_no":null,"error":"Cannot decode broken.txt as UTF-8; check its encoding","searchable":false}
  ],
  "failed": 1
}
```

`created`, `updated`, and `unchanged` mean the document was stored; **none means it can answer a question yet**. Display these as “已导入，尚未生成问答答案”. The separate question API can return candidate passages, but its `answer` is `null`. Failed files return a per-file reason and do not replace their previous active version. A partial batch still uses HTTP 200; check `failed` and every file's `status`. Unknown knowledge base returns 404; malformed batch/path returns 422 **before any file is written**.

Current limits: only UTF-8 MD/TXT (BOM accepted); at most 20 files per request and 5 MiB per file. Exact originals are saved in local SQLite by default. Upload is synchronous, so there is no `job_id`, progress polling, persistent search index, delete endpoint, authentication, or production-scale storage yet. Run the backend on loopback or another trusted development network only; do not expose this unauthenticated API to the public Internet.

B-side first page can now implement: select/create knowledge base, choose one or several files (optionally a folder), submit, show per-file result, refresh the document list. Directory tree, document detail, deletion, index progress, and actual Q&A should be separate increments.
