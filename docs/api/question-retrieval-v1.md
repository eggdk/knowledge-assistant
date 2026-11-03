# 提问接口 v1：供前端联调的原文检索

状态：2026-11-03 已实现并测试。A/B 双方约定首版**只返回相关原文片段**，不生成模型答案。这个接口让插件能把用户的问题送到后端，也让前端能显示「找到的候选资料」。它不是课程要求的最终多轮问答。

## 请求

`POST /api/knowledge-bases/{kb_id}/questions`，`Content-Type: application/json`。

```json
{
  "question": "Agent Insight 的 Trace 在哪里查看？",
  "limit": 5
}
```

- `kb_id`：已创建的知识库 ID，从建库或列库接口取得。
- `question`：用户输入，去掉首尾空白后不能为空；原始长度最多 1000 字符。
- `limit`：可省略，默认 5；范围 1～20。

## 成功响应

下例仅说明字段形状；具体原文、行号和排序分数取决于该知识库实际导入的资料。

```json
{
  "question": "Agent Insight 的 Trace 在哪里查看？",
  "answer": null,
  "answer_status": "not_generated",
  "matches": [
    {
      "chunk_id": "chk_示例标识",
      "relative_path": "view-traces.md",
      "version_no": 1,
      "start_line": 12,
      "end_line": 20,
      "heading": "链路追踪 / 列表",
      "content": "这里是该知识库里匹配到的原文片段……",
      "score": 1.23
    }
  ]
}
```

`matches` 只包含这个知识库**当前版本**的原文块，按相关度排序。`score` 只是排序分数，不能当作答案可信度。`answer: null` 和 `answer_status: "not_generated"` 表示后端**尚未回答**；前端可把 `matches` 标为「相关资料」，不能把它们直接排版成「助手回答」或已核验的「引用」。没有词面匹配时 `matches: []`，依然是 HTTP 200。

知识库不存在返回 404；空白问题、超长问题或非法 `limit` 返回 422。请求不保存会话，也不调用大模型，没有流式事件、反馈或引用详情接口。

## B 岗本地接线示例

在 `apps/web` 启动 Vite 开发服务时，`vite.config.ts` 已将 `/api` 转发到本机 `http://127.0.0.1:8000`。先启动 FastAPI，再启动 Vite。插件页面可向**同源相对路径**发送：

```ts
type SourceMatch = {
  chunk_id: string
  relative_path: string
  version_no: number
  start_line: number
  end_line: number
  heading: string
  content: string
  score: number
}

type QuestionResponse = {
  question: string
  answer: string | null
  answer_status: 'not_generated'
  matches: SourceMatch[]
}

async function askQuestion(kbId: string, question: string): Promise<QuestionResponse> {
  const response = await fetch(`/api/knowledge-bases/${encodeURIComponent(kbId)}/questions`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ question }),
  })
  if (!response.ok) throw new Error(`提问失败：HTTP ${response.status}`)
  return response.json() as Promise<QuestionResponse>
}
```

前端需要先确定 `kbId` 从哪里来：固定演示库、宿主页面传入、或让用户选择知识库，三者只能先选一种并写明。不要在网页里写入模型 API Key。

上面的代理**只用于 Vite 本地开发**。构建后的插件若放到另一个域名或 Agent Insight 里，仍要为其部署环境配置同源 `/api` 反向代理，或商定受限的跨域规则；目前没有配置生产跨域。前端发送按钮在队友的 `app` 分支中仍是禁用的静态预览，需要 B 岗按此接口实现输入、加载、失败提示和结果列表。后端不负责替 B 岗直接修改聊天界面。

## 联调通过标准

1. 建一个知识库，上传一份 MD/TXT，记下 `kb_id`。
2. 从插件提交一个文档确实含有的关键词；浏览器网络请求发往 `/api/knowledge-bases/{kb_id}/questions`，得到 200、`answer: null` 和非空 `matches`。
3. 页面展示原文、文件名和行号，并明确提示「暂未生成答案」。
4. 输入资料没有的词，得到空列表；输入空白问题时，前端阻止提交或清楚显示 422。
5. 另一知识库里的文件不应出现在当前知识库的结果里。
