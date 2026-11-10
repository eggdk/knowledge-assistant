# 提问接口 v1：供前端联调的原文检索

状态：2026-11-03 已实现并测试。A/B 双方约定首版**只返回相关原文片段**，不生成模型答案。这个接口让插件能把用户的问题送到后端，也让前端能显示「找到的候选资料」。它不是课程要求的最终多轮问答。

2026-11-10 更新：底层检索会清理少量通用问法并提升完整主题标题匹配，接口字段不变，返回的 `question` 保留原问题。`/answers` 同样使用该排序，见[检索修复说明](../learning/12-broad-question-retrieval-fix.md)。

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

**2026-11-03 对齐决定：**首版由每个宿主网页配置一个 `kbId`，访客不选库。宿主脚本标签使用 `data-kb-id="kb_..."`；`embed.js` 把它传入插件 iframe 的 `kbId` 查询参数。插件页面已经将该参数读入 `src/main.tsx` 的 `kbId`；B 岗接发送按钮时用它调用上面的 `askQuestion`。没有配置时不发送请求，页面已显示配置提示。演示宿主页可用 `/?kbId=本机的ID` 设置，不需要修改共享源码；不同电脑应使用各自本地建库得到的 ID。不要在网页里写入模型 API Key，也不要把 `kbId` 当作访问权限验证。

上面的代理**只用于 Vite 本地开发**。构建后的插件若放到另一个域名或 Agent Insight 里，仍要为其部署环境配置同源 `/api` 反向代理，或商定受限的跨域规则；目前没有配置生产跨域。当前 `main` 中的插件已接通 `/answers`；缺少模型密钥时会改用本页的 `/questions` 展示候选原文，输入、加载和失败提示已接线。

## 联调通过标准

1. 建一个知识库，上传一份 MD/TXT，记下 `kb_id`。
2. 宿主配置 `data-kb-id`（本地演示页可用 `?kbId=...`）；从插件提交一个文档确实含有的关键词。浏览器网络请求发往 `/api/knowledge-bases/{kb_id}/questions`，得到 200、`answer: null` 和非空 `matches`。
3. 页面展示原文、文件名和行号，并明确提示「暂未生成答案」。
4. 输入资料没有的词，得到空列表；输入空白问题时，前端阻止提交或清楚显示 422。
5. 另一知识库里的文件不应出现在当前知识库的结果里。
