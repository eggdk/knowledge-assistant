"""The demo evaluation must find actual answer spans, not just file names."""

import json

import pytest

from app.evaluation import DEFAULT_DATASET, evaluate_dataset, load_cases, summarize


def test_demo_evaluation_finds_labeled_answer_chunks() -> None:
    results = evaluate_dataset(DEFAULT_DATASET)
    counts = summarize(results)

    assert counts["positive_total"] == 12
    assert counts["negative_total"] == 4
    assert counts["top1"] >= 10
    assert counts["top5"] == 12
    assert {result.case.case_id for result in results if result.answer_rank is None} == {
        "N01", "N02", "N03", "N04"
    }


def test_broken_answer_label_is_reported_instead_of_counted_as_a_miss(tmp_path) -> None:
    dataset = tmp_path / "dataset"
    (dataset / "docs").mkdir(parents=True)
    (dataset / "docs" / "guide.md").write_text("# 标题\n真实答案。", encoding="utf-8")
    (dataset / "cases.json").write_text(
        json.dumps([
            {
                "id": "P01",
                "question": "答案是什么？",
                "source": "guide.md",
                "answer_text": "错误的标注",
            }
        ], ensure_ascii=False),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="label is absent"):
        evaluate_dataset(dataset)


def test_duplicate_case_ids_are_rejected(tmp_path) -> None:
    cases = tmp_path / "cases.json"
    cases.write_text(
        json.dumps([
            {"id": "N01", "question": "第一题", "source": None, "answer_text": None},
            {"id": "N01", "question": "第二题", "source": None, "answer_text": None},
        ], ensure_ascii=False),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="unique"):
        load_cases(cases)


def test_alternative_answer_span_counts_when_it_reaches_first_place(tmp_path) -> None:
    dataset = tmp_path / "dataset"
    (dataset / "docs").mkdir(parents=True)
    (dataset / "docs" / "guide.md").write_text(
        "# 指南\n## A\n旧表达。\n## B\n替代答案。", encoding="utf-8"
    )
    (dataset / "cases.json").write_text(
        json.dumps([
            {
                "id": "P01",
                "question": "替代答案",
                "source": "guide.md",
                "answer_text": "旧表达",
                "also_accept": ["替代答案"],
            }
        ], ensure_ascii=False),
        encoding="utf-8",
    )

    assert evaluate_dataset(dataset)[0].answer_rank == 1


def test_pinned_agent_insight_labels_are_valid_and_retrievable() -> None:
    dataset = DEFAULT_DATASET.parent / "agent_insight"
    counts = summarize(evaluate_dataset(dataset))

    assert counts["positive_total"] == 18
    assert counts["negative_total"] == 5
    assert counts["top1"] >= 12
    assert counts["top5"] >= 17
