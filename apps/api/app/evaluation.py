"""Repeatable, answer-span-aware evaluation of the local keyword retriever.

Run from apps/api: python -m app.evaluation
The bundled dataset is illustrative; replace it with team-labeled questions.
"""

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory

from app.import_service import import_directory
from app.knowledge_store import create_knowledge_base, list_active_chunks
from app.retrieval import search_knowledge_base


DEFAULT_DATASET = Path(__file__).resolve().parents[3] / "evals" / "demo"


@dataclass(frozen=True)
class EvalCase:
    case_id: str
    question: str
    source: str | None
    answer_text: str | None


@dataclass(frozen=True)
class EvalResult:
    case: EvalCase
    answer_rank: int | None
    first_source: str | None
    first_excerpt: str | None
    hit_count: int


def load_cases(path: Path) -> list[EvalCase]:
    """Load labels kept outside the importable document folder."""
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, list) or not raw:
        raise ValueError("Cases must be a nonempty JSON array")
    cases: list[EvalCase] = []
    seen_ids: set[str] = set()
    for item in raw:
        if not isinstance(item, dict):
            raise ValueError("Each case must be an object")
        case_id = item.get("id")
        question = item.get("question")
        source = item.get("source")
        answer_text = item.get("answer_text")
        if not isinstance(case_id, str) or not case_id.strip() or case_id in seen_ids:
            raise ValueError("Case IDs must be nonempty and unique")
        if not isinstance(question, str) or not question.strip():
            raise ValueError(f"Case {case_id} needs a question")
        if source is None:
            if answer_text is not None:
                raise ValueError(f"Negative case {case_id} must not have answer_text")
        elif not isinstance(source, str) or not source.strip() or not isinstance(answer_text, str) or not answer_text.strip():
            raise ValueError(f"Positive case {case_id} needs source and answer_text")
        seen_ids.add(case_id)
        cases.append(EvalCase(case_id, question, source, answer_text))
    return cases


def evaluate_dataset(dataset: Path) -> list[EvalResult]:
    """Import a fresh copy so old local data cannot affect the score."""
    cases = load_cases(dataset / "cases.json")
    with TemporaryDirectory(prefix="knowledge-eval-") as temporary:
        database = Path(temporary) / "evaluation.sqlite3"
        kb_id = create_knowledge_base(database, "Isolated retrieval evaluation")
        outcomes = import_directory(database, kb_id, dataset / "docs", retain_original=False)
        if not outcomes or any(outcome.status == "failed" for outcome in outcomes):
            raise ValueError("Evaluation documents are missing or could not be imported")

        chunks = list_active_chunks(database, kb_id)
        for case in cases:
            if case.source is not None and not any(
                chunk.relative_path == case.source and case.answer_text in chunk.content
                for chunk in chunks
            ):
                raise ValueError(
                    f"Case {case.case_id} label is absent from one source chunk: "
                    f"{case.source} / {case.answer_text}"
                )

        results = []
        for case in cases:
            hits = search_knowledge_base(database, kb_id, case.question, limit=5)
            answer_rank = next(
                (
                    rank
                    for rank, hit in enumerate(hits, start=1)
                    if hit.chunk.relative_path == case.source
                    and case.answer_text is not None
                    and case.answer_text in hit.chunk.content
                ),
                None,
            )
            results.append(
                EvalResult(
                    case=case,
                    answer_rank=answer_rank,
                    first_source=hits[0].chunk.relative_path if hits else None,
                    first_excerpt=" ".join(hits[0].chunk.content.split())[:80] if hits else None,
                    hit_count=len(hits),
                )
            )
        return results


def summarize(results: list[EvalResult]) -> dict[str, int]:
    positives = [result for result in results if result.case.source is not None]
    negatives = [result for result in results if result.case.source is None]
    return {
        "positive_total": len(positives),
        "top1": sum(result.answer_rank == 1 for result in positives),
        "top5": sum(result.answer_rank is not None for result in positives),
        "negative_total": len(negatives),
        "no_hit": sum(result.hit_count == 0 for result in negatives),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Evaluate local keyword retrieval")
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    args = parser.parse_args(argv)
    try:
        results = evaluate_dataset(args.dataset)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        parser.error(str(exc))
    counts = summarize(results)
    print(
        f"Answer chunk Top-1: {counts['top1']}/{counts['positive_total']}; "
        f"Top-5: {counts['top5']}/{counts['positive_total']}; "
        f"negative no-hit: {counts['no_hit']}/{counts['negative_total']}"
    )
    for result in results:
        outcome = (
            "NO-HIT" if result.hit_count == 0 else f"FALSE-HIT ({result.hit_count})"
        ) if result.case.source is None else (
            f"RANK {result.answer_rank}" if result.answer_rank else "MISS"
        )
        print(f"{result.case.case_id}: {outcome} | {result.case.question}")
        if result.first_source:
            print(f"  first: {result.first_source} | {result.first_excerpt}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
