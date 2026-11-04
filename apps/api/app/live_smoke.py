"""Run a small, opt-in real Qwen smoke test on pinned public Agent Insight docs.

Run from apps/api: python -m app.live_smoke
"""

import argparse
import getpass
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4

from app.answer_generation import MODEL_NAME, ModelAnswerError, generate_answer
from app.evaluation import load_cases
from app.import_service import import_directory
from app.knowledge_store import create_knowledge_base
from app.retrieval import search_knowledge_base


REPO_ROOT = Path(__file__).resolve().parents[3]
DATASET = REPO_ROOT / "evals" / "agent_insight"
DEFAULT_CASE_IDS = ("T04", "D03", "N04")
REGION_BASE_URLS = {
    "beijing": "https://dashscope.aliyuncs.com/compatible-mode/v1",
    "singapore": "https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
    "us": "https://dashscope-us.aliyuncs.com/compatible-mode/v1",
    "hongkong": "https://cn-hongkong.dashscope.aliyuncs.com/compatible-mode/v1",
}
REGION_CHOICES = {"1": "beijing", "2": "singapore", "3": "us", "4": "hongkong"}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Small real Qwen test; no key is saved")
    parser.add_argument("--cases", nargs="+", default=list(DEFAULT_CASE_IDS))
    parser.add_argument("--dry-run", action="store_true", help="Inspect retrieval without calling Qwen")
    parser.add_argument("--region", choices=REGION_BASE_URLS, help="API Key region")
    args = parser.parse_args(argv)
    if not 1 <= len(args.cases) <= 3 or len(set(args.cases)) != len(args.cases):
        parser.error("Choose one to three different case IDs per run")

    cases_by_id = {case.case_id: case for case in load_cases(DATASET / "cases.json")}
    unknown = [case_id for case_id in args.cases if case_id not in cases_by_id]
    if unknown:
        parser.error(f"Unknown case IDs: {', '.join(unknown)}")

    storage = (REPO_ROOT / "storage").resolve()
    storage.mkdir(exist_ok=True)
    with TemporaryDirectory(prefix="qwen-smoke-", dir=storage) as temporary:
        temporary_path = Path(temporary).resolve()
        if not temporary_path.is_relative_to(storage):
            raise RuntimeError("Temporary database escaped the storage directory")
        database = temporary_path / "smoke.sqlite3"
        kb_id = create_knowledge_base(database, "Public Agent Insight smoke test")
        outcomes = import_directory(database, kb_id, DATASET / "docs", retain_original=False)
        if not outcomes or any(outcome.status == "failed" for outcome in outcomes):
            raise RuntimeError("Could not import the pinned Agent Insight documents")

        selected = [
            (
                cases_by_id[case_id],
                search_knowledge_base(database, kb_id, cases_by_id[case_id].question, limit=5),
            )
            for case_id in args.cases
        ]
        print(f"模型：{MODEL_NAME}；测试题：{', '.join(args.cases)}")
        print("最多调用模型三次；每次输出最多 600 Token。")
        for case, hits in selected:
            print(f"{case.case_id}: {case.question} | 检索到 {len(hits)} 个片段")
            if args.dry_run:
                for index, hit in enumerate(hits, start=1):
                    chunk = hit.chunk
                    print(
                        f"  S{index}: {chunk.relative_path} "
                        f"L{chunk.start_line}-{chunk.end_line}"
                    )
        if args.dry_run:
            return 0

        supplied_base_url = False
        if not os.environ.get("DASHSCOPE_BASE_URL", "").strip():
            region = args.region
            if region is None:
                if not sys.stdin.isatty():
                    print("请在可输入内容的终端选择 API Key 地域。", file=sys.stderr)
                    return 2
                selection = input("Key 地域：1 北京 / 2 新加坡 / 3 美国 / 4 中国香港：").strip()
                region = REGION_CHOICES.get(selection)
            if region not in REGION_BASE_URLS:
                print("地域未选择；请先在百炼密钥管理页查看。", file=sys.stderr)
                return 2
            os.environ["DASHSCOPE_BASE_URL"] = REGION_BASE_URLS[region]
            supplied_base_url = True

        supplied_key = False
        if not os.environ.get("DASHSCOPE_API_KEY", "").strip():
            if not sys.stdin.isatty():
                print("请在可输入内容的终端运行，以便安全输入 API Key。", file=sys.stderr)
                return 2
            key = getpass.getpass("粘贴按量付费的百炼 API Key（输入不显示）：").strip()
            if not key:
                print("未输入 API Key，因此没有调用模型。", file=sys.stderr)
                return 2
            os.environ["DASHSCOPE_API_KEY"] = key
            supplied_key = True

        records = []
        failed = False
        try:
            for case, hits in selected:
                try:
                    answer = generate_answer(case.question, hits)
                except ModelAnswerError as exc:
                    print(f"{case.case_id}: 模型调用失败：{exc}", file=sys.stderr)
                    failed = True
                    break
                citations = [
                    {
                        "label": label,
                        "file": hit.chunk.relative_path,
                        "version": hit.chunk.version_no,
                        "start_line": hit.chunk.start_line,
                        "end_line": hit.chunk.end_line,
                    }
                    for label, hit in zip(answer.citation_ids, answer.cited_hits, strict=True)
                ]
                print(f"\n{case.case_id}: {answer.status}\n{answer.answer}")
                print(f"引用：{citations}；Token 用量：{answer.usage}")
                print(f"人工对照：{case.source} | {case.answer_text}")
                records.append(
                    {
                        "id": case.case_id,
                        "question": case.question,
                        "answer": answer.answer,
                        "status": answer.status,
                        "citations": citations,
                        "usage": answer.usage,
                        "reference_source": case.source,
                        "reference_text": case.answer_text,
                    }
                )
        finally:
            if supplied_key:
                os.environ.pop("DASHSCOPE_API_KEY", None)
            if supplied_base_url:
                os.environ.pop("DASHSCOPE_BASE_URL", None)

    if records:
        filename = f"qwen-smoke-{datetime.now():%Y%m%d-%H%M%S}-{uuid4().hex[:6]}.json"
        report = storage / filename
        report.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\n公开资料的测试结果已保存：{report}")
        print("需要人工对照参考文本；引用编号正确不等于答案正确。")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
