# 生成答案接口 v1（A 岗）

首版模型选择：阿里云百炼 `qwen3.7-plus`，使用按量付费的模型 API。知识库仍保存在本地 SQLite；每次只把问题及检索到的少量当前版本片段发给模型。模型的引用编号由后端核对；这一步尚不能自动证明答案的每句话都正确。

## 调用流程

`POST /api/knowledge-bases/{kb_id}/answers`，请求 JSON：

```json
{"question":"Trace 在哪里查看？","limit":5}
```

后端先在指定知识库检索原文，再向千问请求 JSON 答案。成功响应示例：

```json
{
  "question": "Trace 在哪里查看？",
  "answer": "在 Trace 页面查看调用记录。",
  "answer_status": "generated",
  "model": "qwen3.7-plus",
  "citations": [
    {
      "label": "S1",
      "chunk_id": "chk_...",
      "relative_path": "guide.md",
      "version_no": 1,
      "start_line": 1,
      "end_line": 2,
      "heading": "Trace",
      "content": "Trace 页面显示调用记录。",
      "score": 1.0
    }
  ]
}
```

没有匹配片段时，返回 HTTP 200、`answer_status: "insufficient_evidence"`、固定的说明文字、`model: null` 与空引用列表，且不会调用模型。模型判断资料不足时也返回 `insufficient_evidence`，但 `model` 是 `qwen3.7-plus`。

缺少 API Key 且存在匹配片段时返回 503；模型服务失败或返回不合法的答案时返回 502。知识库不存在返回 404；空白问题和非法 `limit` 返回 422。`limit` 默认 5，范围 1～8。

原有 `POST /api/knowledge-bases/{kb_id}/questions` 继续只返回原文片段，供 B 岗现有页面联调。B 岗准备展示模型答案时，再调用 `/answers` 并根据 `answer_status` 显示答案或“资料不足”；引用要显示文件名和行号。

`citations[].label` 对应答案文字中的 `[S1]` 等编号；前端应按编号把答案中的引用与文件、行号关联。引用列表的顺序不一定等于编号大小，不能靠数组下标猜编号。

## 多轮追问

`/answers` 和 `/questions` 均接受可选的 `history`。前端从当前知识库的对话中取最近三条已发送的用户问题，按从旧到新排序，和当前问题一起提交。

```json
{
  "question": "刚才那个实验失败后怎么重试？",
  "history": ["Agent Insight 如何管理实验？"],
  "limit": 5
}
```

历史问题每条最多 1000 个字符，去掉首尾空白后须有内容，最多传三条。越界返回 `422`。切换知识库或开始新对话时清空 `history`。旧客户端可省略该字段。

后端识别“刚才”“它”“前者”“后者”等指代表达后，从最近一个独立问题起取上下文，和当前问题一起检索。千问使用这段上下文理解指代，答案和引用依据本次检索的资料。独立新问题使用单轮检索。首版依赖显式指代表达，省略主语但缺少这类表达时仍可能需要用户补全问题。

历史随请求传入，服务端没有会话记录。每次生成仍发起一次模型调用。问答回退到 `/questions` 时，前端传相同的 `question` 和 `history`，让检索延续当前话题。

## 本地配置

由后端运行环境提供 `DASHSCOPE_API_KEY`。仓库的 `.gitignore` 已排除 `.env` 文件；不要把密钥放入源码、前端或 GitHub。默认请求北京地域的 `https://dashscope.aliyuncs.com/compatible-mode/v1`；若密钥属于其他地域，将 `DASHSCOPE_BASE_URL` 设置为该地域的 OpenAI 兼容 Base URL。密钥与地域必须匹配。请使用普通按量付费模型 API 的密钥，不要把 Coding Plan 或 Token Plan 的密钥用于应用后端。

参考：[阿里云 Base URL 总览](https://help.aliyun.com/zh/model-studio/base-url)、[千问结构化输出](https://help.aliyun.com/zh/model-studio/qwen-structured-output)。

目前自动化测试使用模拟模型响应，不消耗费用；真实账号、网络、费用、实际回答质量仍需配置密钥后做一次人工联调及固定题目评测。

当前接口为本地课程联调准备，还没有访客鉴权或调用限流。若要公开部署生成接口，需要先限制谁能调用，避免他人消耗模型额度。
