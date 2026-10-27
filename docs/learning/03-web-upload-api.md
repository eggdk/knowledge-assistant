# 第 3 课：为什么有了命令行，还要做上传接口

命令行适合 A 岗在自己的电脑上导入文件；B 岗做的网页不能直接读取后端电脑的任意目录。因此我们让浏览器把**用户选中的文件**发送到后端，后端仍调用上一课的同一个 `import_document()`。这样两种入口的编码检查、版本判断和原件保存规则相同。

## 你现在可以不用写前端，先从接口页试

在仓库根目录打开 PowerShell：

```powershell
Set-Location apps/api
& ..\..\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

打开 `http://127.0.0.1:8000/docs`：

1. 找到 `POST /api/knowledge-bases`，点 `Try it out`，填 `{"name":"我的测试库"}`，执行后记下 `kb_...` 编号。
2. 找到 `POST /api/knowledge-bases/{kb_id}/documents/import`，填编号，选择 `examples/sample_docs` 中的一份 MD/TXT 文件；`relative_paths` 不填也可以。执行后应看到 `created` 和 `searchable: false`。
3. 再上传同一份文件，应看到 `unchanged`；到 `GET /api/knowledge-bases/{kb_id}/documents` 查看列表。
4. `Ctrl+C` 停止服务器。数据库默认保存在仓库的 `storage/knowledge.sqlite3`，不会提交到 Git。

`files` 必须通过浏览器的 **Choose Files / 选择文件** 按钮选取；在文本框里输入 `D:\...\intro.md` 只会把路径当作普通文字发送，后端会报 `Expected UploadFile, received: str`。`relative_paths` 是可选的，留空时使用所选文件名。如果刚更新代码后仍看到文本框，先停止并重新启动 Uvicorn，再强制刷新 `/docs`。正确选择文件后，页面自动生成的 Curl 示例中，文件名前会有 `@`；不用自己运行 Curl。

## 一次上传经过哪些代码

`app/main.py` 接入路由 → `app/api_routes.py` 校验知识库和表单字段 → `app/knowledge_store.py` 调用与 CLI 共用的导入函数 → `app/text_parser.py` 解析正文 → SQLite 记录版本和原件 → API 把逐文件结果返回网页。

两个特别重要的边界：

- `searchable: false` 不是报错，而是诚实地告诉页面：目前只有“存资料”，还没有“建检索索引”。
- 整批请求结构有问题（例如路径数量不匹配、路径含 `..`）时，后端会在写入前拒绝；单个文件内容有问题时，只让该文件失败，其他文件继续导入。

后端暂时限制每次 20 份文件、每份 5 MiB，避免本地开发时误传大文件。等 Word/Excel/PDF 和后台任务阶段再重新评估限制。完整字段和给 B 岗的前端示例见 [`docs/api/knowledge-base-v1.md`](../api/knowledge-base-v1.md)。
