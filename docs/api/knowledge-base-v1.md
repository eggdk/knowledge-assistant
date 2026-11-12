# Knowledge-base HTTP API v1 — A/B handoff

Updated 2026-11-10: the upload and document-list responses now report actual current-version retrieval readiness. This page describes the storage/import contract. The separate [question API v1](question-retrieval-v1.md) returns candidate passages; the [answer API](answer-generation-v1.md) can generate a cited answer when the backend model key is configured.

Base URL when running locally: `http://127.0.0.1:8000`. Interactive API page: `/docs`.

| Action | Method and path | Request | Response |
|---|---|---|---|
| Create a knowledge base | `POST /api/knowledge-bases` | JSON `{"name":"课程资料"}` | `201`, `{"id":"kb_...","name":"课程资料"}` |
| List knowledge bases | `GET /api/knowledge-bases` | None | Array of `{id,name}` |
| List imported documents | `GET /api/knowledge-bases/{kb_id}/documents` | None | Array of `{id,relative_path,version_no,sha256,imported_at,searchable}` |
| Upload selected files | `POST /api/knowledge-bases/{kb_id}/documents/import` | `multipart/form-data` | `{files:[...],failed:N}` |
| Remove a document | `DELETE /api/knowledge-bases/{kb_id}/documents/{document_id}` | None | `204` with an empty body, or `404` |

## 删除与恢复

删除请求使用文档列表里的 `id` 作为 `document_id`。收到 `204` 后刷新列表，成功响应没有 JSON。重复删除同一份文档仍返回 `204`。知识库不存在、文档不存在或文档属于其他知识库时返回 `404`。

删除成功后，文档从列表、重建范围和后续问答检索中移除。SQLite 单独记录删除状态，保留原件、版本和文本块。已有数据库会在连接时创建所需的表和视图。

在同一知识库重新上传相同的相对路径，可恢复同一个文档 ID。文件字节与删除前的最新版本一致时返回 `unchanged` 并沿用版本号，有变化时返回 `updated` 并增加版本号。成功后刷新列表即可看到恢复的文档。上传失败时文档保持删除状态。

## 上传

网页上传和 CLI 目录导入使用同一套格式规则，扩展名大小写均可：

- `.md`、`.txt`：读取 UTF-8 文本，接受 BOM。
- `.docx`：按正文顺序提取段落和表格中的文字。
- `.xlsx`：逐工作表读取单元格，公式使用文件中已缓存的结果。没有缓存的公式值不会被重新计算。
- `.pdf`：逐页提取已有的文字并标出原始页码。纯扫描件须先做 OCR，加密文件须先解除保护。

原件仍按原路径和字节保存。引用行号指提取后的文本行，PDF 的原始页码和 Excel 的工作表名写入提取文本。旧版 `.doc`、`.xls` 请先转存为 `.docx`、`.xlsx`。

### 多格式导入联调

1. 同步 `main` 后，从仓库根目录运行 `& .\.venv\Scripts\python.exe -m pip install -r apps/api/requirements.txt`，然后重启后端。
2. 在管理页的单文件、多文件和文件夹选择中开放 `.docx`、`.xlsx`、`.pdf`，沿用现有的 `files`、`relative_paths` 和逐文件结果展示。HTTP 200 也可能包含部分失败，以每个文件的 `status` 和 `error` 为准。
3. 每种格式准备一份含有独有关键词的文件，上传后确认 `searchable: true`，再通过问答插件提问并展开引用。可先用 `/docs` 的上传和 `/questions` 接口验证检索，这两步无需模型密钥。
4. 将坏文件和正常文件放在同一批上传，确认页面分别显示成功和失败。若坏文件与已导入文件同路径，刷新列表后应仍能看到之前的版本。

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
    {"relative_path":"manual/intro.md","status":"created","version_no":1,"error":null,"searchable":true},
    {"relative_path":"broken.txt","status":"failed","version_no":null,"error":"Cannot decode broken.txt as UTF-8; check its encoding","searchable":false}
  ],
  "failed": 1
}
```

`created`, `updated`, and `unchanged` mean the document was stored or its existing version retained. `searchable: true` means at least one text chunk exists for the current document version and current chunking strategy, so it can participate in retrieval. Display this as “已导入，可检索”; it does not promise that a particular question will match, that a model key is configured, or that an answer is correct. Old versions or old chunking strategies do not make the current version searchable. Older imports without current chunks return false in the document list; reimporting the same bytes backfills chunks without inventing a new document version.

Since the `mdtxt-v2` update, existing databases can use `python -m app.cli chunks rebuild --kb YOUR_KB_ID` from `apps/api` to regenerate current chunks from saved text, preserving originals and document versions. See the [upgrade explanation](../learning/13-complete-chunk-boundaries.md). Until rebuilding or reimporting, an old database may have no chunks for the current strategy.

Failed uploads return `searchable: false` for that **attempt**, and do not replace a previously valid active version. Refresh the document list to see the existing document's real state; do not mark it unavailable simply because an update failed. Empty/whitespace-only files are rejected. A partial batch still uses HTTP 200; check `failed` and every file's `status`. Unknown knowledge base returns 404; malformed batch/path returns 422 **before any file is written**.

Current HTTP limits: at most 20 files per request and 5 MiB per file. Exact originals are saved in local SQLite by default. Upload is synchronous, so there is no `job_id`, progress polling, persistent search index, authentication, or production-scale storage yet. Run the backend on loopback or another trusted development network only; do not expose this unauthenticated API to the public Internet.

B-side first management page can implement: select/create knowledge base, choose one or several files (optionally a folder), submit, show per-file result, refresh the document list. The delete button can use the endpoint above. Directory tree, document detail and index progress remain separate increments. The existing widget already calls the answer API. See the [backend update and diagnosis](../learning/11-search-status-and-retrieval-diagnostics.md) for examples.
