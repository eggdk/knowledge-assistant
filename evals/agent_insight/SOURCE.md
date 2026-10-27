# Agent Insight 真实文档检索评测集

课程任务要求把问答插件集成到 Agent Insight，但课程任务文件没有指定仓库地址、分支或文档包。本评测集暂用公开的 [openEuler Agent Insight GitHub 镜像](https://github.com/openeuler-mirror/agent-insight)，**不声称已经确认这是老师要求运行的具体版本**。

- 上游提交：[`bfdd20131330c495707220dc11d7facc9795a3b4`](https://github.com/openeuler-mirror/agent-insight/tree/bfdd20131330c495707220dc11d7facc9795a3b4)
- 获取日期：2026-10-27。
- 许可：仓库 `LICENSE` 为 MIT；原许可文本保存在本目录 `UPSTREAM_LICENSE.txt`。四篇文档原文未改动，仅为评测复制到 `docs/` 并缩短了本地文件名。
- 答案标注：`cases.json` 由课程团队编写，放在导入目录之外；正例标注原文短句，负例标注无答案。它们不属于上游官方评测集。

| 本地文件 | 上游原路径 | SHA-256 |
| --- | --- | --- |
| `view-traces.md` | [`docs/user-guide/observability/view-traces.md`](https://github.com/openeuler-mirror/agent-insight/blob/bfdd20131330c495707220dc11d7facc9795a3b4/docs/user-guide/observability/view-traces.md) | `4a6393467f080ae5f5d53652d7bb6b5dc24cb165c2d8ec833972dbf911aee5b8` |
| `datasets.md` | [`docs/user-guide/evaluation/datasets.md`](https://github.com/openeuler-mirror/agent-insight/blob/bfdd20131330c495707220dc11d7facc9795a3b4/docs/user-guide/evaluation/datasets.md) | `072b1be4b7465ee96583698881cedf2fc1f0a1a153a21f838b22f823989a3106` |
| `experiments.md` | [`docs/user-guide/evaluation/experiments.md`](https://github.com/openeuler-mirror/agent-insight/blob/bfdd20131330c495707220dc11d7facc9795a3b4/docs/user-guide/evaluation/experiments.md) | `3d03eaf6c48c0ee7961628b60832dbac0dac398e0387433f94a273198f0238ef` |
| `model-registry.md` | [`docs/user-guide/settings/model-registry.md`](https://github.com/openeuler-mirror/agent-insight/blob/bfdd20131330c495707220dc11d7facc9795a3b4/docs/user-guide/settings/model-registry.md) | `8cf3ae6b2ef46a1790bffc16449471906a912081e4a78291433f62c36df8fdfa` |

在 `apps/api` 运行：

```powershell
& ..\..\.venv\Scripts\python.exe -m app.evaluation --dataset ..\..\evals\agent_insight
```

这次只检查 MD 原文块能否被找到。它不验证网页界面，也不验证生成答案的事实准确性。文档是上游快照，图片及相对链接仍指向上游目录结构；本地导入仅处理文本。
