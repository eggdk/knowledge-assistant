# 01 后端第一步：一个真实的 HTTP 接口

本页对应 `apps/api/app/main.py` 和 `apps/api/tests/test_health.py`。当前项目只完成了后端基础，不具备知识库问答能力。

## 先看整体路线

```text
浏览器或测试代码发出 GET /health
    → Uvicorn 接收 HTTP 请求
    → FastAPI 根据 @app.get("/health") 找到 health 函数
    → health 返回 Python 字典 {"status": "ok"}
    → FastAPI 将字典转成 JSON 响应
```

`GET` 的意思是“读取信息”；`/health` 是这个接口的地址。它只告诉我们后端进程能正常接收和回答请求，**不代表模型、文件解析或数据库业务已经完成**。

## 关键代码怎么读

- `app = FastAPI(...)`：创建后端应用对象；Uvicorn 会从 `app.main:app` 找到它。
- `@app.get("/health")`：把浏览器的 `GET /health` 请求交给下面的 `health` 函数。
- `def health() -> dict[str, str]`：声明一个函数，返回值应是“字符串键到字符串值”的字典。
- `return {"status": "ok"}`：返回实际数据；FastAPI 负责把它序列化成 JSON。

测试没有手工点击网页，而是用 `TestClient` 模拟 HTTP 请求，再分别检查状态码 `200` 和 JSON 内容。这样以后改代码时，只要运行 `pytest` 就能快速发现基础接口是否坏了。

SQLite 测试使用 pytest 提供的 `tmp_path` 临时目录：建一张仅供测试的表，写入中文，再读回来核对。它证明当前 Python 环境能使用 SQLite，**不是正式的知识库表设计**。

## 运行顺序（Windows PowerShell）

从仓库根目录执行 `Set-Location apps/api`，然后：

```powershell
& ..\..\.venv\Scripts\python.exe -m pytest -q
& ..\..\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

第二条命令启动后，在浏览器打开 <http://127.0.0.1:8000/health>，应看到 `{"status":"ok"}`。按 `Ctrl+C` 停止。

## 一个不用手写代码的理解检查

如果把路由改成 `@app.get("/ready")`，但测试仍请求 `/health`，你预计测试会怎样？先自己想一下，再运行测试观察错误输出。看完后把路由改回去。
