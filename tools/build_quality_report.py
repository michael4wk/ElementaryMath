#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import List


def read_jsonl(path: Path) -> List[dict]:
    rows: List[dict] = []
    if not path.exists():
        return rows
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
    return rows


def ratio(n: int, d: int) -> float:
    if d == 0:
        return 0.0
    return round(n * 100.0 / d, 2)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", type=str, default=".")
    args = parser.parse_args()

    project_root = Path(args.project_root).resolve()
    topics = read_jsonl(project_root / "artifacts" / "curated" / "topics.jsonl")
    problems = read_jsonl(project_root / "artifacts" / "curated" / "problems.jsonl")
    explanations = read_jsonl(project_root / "artifacts" / "curated" / "explanations.jsonl")

    empty_answer = sum(1 for p in problems if not (p.get("answer") or "").strip())
    empty_analysis = sum(1 for p in problems if not p.get("analysis_steps"))
    formula_only_answer = sum(1 for p in problems if (p.get("answer") or "").strip() == "【公式】")
    formula_in_stem = sum(1 for p in problems if "【公式】" in (p.get("stem") or ""))
    grade_missing = sum(1 for p in problems if not (p.get("grade_band") or "").strip())
    difficulty_missing = sum(1 for p in problems if not (p.get("difficulty") or "").strip())
    method_tag_missing = sum(1 for p in problems if not p.get("method_tags"))
    grade_source_counter = Counter([p.get("grade_source", "none") for p in problems])
    difficulty_source_counter = Counter([p.get("difficulty_source", "none") for p in problems])
    method_tag_source_counter = Counter([p.get("method_tag_source", "none") for p in problems])

    topic_objective_missing = sum(1 for t in topics if not t.get("learning_objectives"))
    topic_mistake_missing = sum(1 for t in topics if not t.get("common_mistakes"))
    explanation_summary_missing = sum(1 for e in explanations if not (e.get("summary") or "").strip())

    top_tag_counter = Counter()
    for p in problems:
        for tag in p.get("method_tags", []):
            top_tag_counter[tag] += 1

    out_dir = project_root / "artifacts" / "quality"
    out_dir.mkdir(parents=True, exist_ok=True)
    report = {
        "topic_count": len(topics),
        "problem_count": len(problems),
        "explanation_count": len(explanations),
        "problem_quality": {
            "empty_answer_count": empty_answer,
            "empty_answer_rate_pct": ratio(empty_answer, len(problems)),
            "empty_analysis_count": empty_analysis,
            "empty_analysis_rate_pct": ratio(empty_analysis, len(problems)),
            "formula_only_answer_count": formula_only_answer,
            "formula_only_answer_rate_pct": ratio(formula_only_answer, len(problems)),
            "formula_in_stem_count": formula_in_stem,
            "formula_in_stem_rate_pct": ratio(formula_in_stem, len(problems)),
            "missing_grade_band_count": grade_missing,
            "missing_grade_band_rate_pct": ratio(grade_missing, len(problems)),
            "missing_difficulty_count": difficulty_missing,
            "missing_difficulty_rate_pct": ratio(difficulty_missing, len(problems)),
            "missing_method_tags_count": method_tag_missing,
            "missing_method_tags_rate_pct": ratio(method_tag_missing, len(problems)),
            "grade_source_distribution": dict(grade_source_counter),
            "difficulty_source_distribution": dict(difficulty_source_counter),
            "method_tag_source_distribution": dict(method_tag_source_counter),
        },
        "topic_quality": {
            "missing_learning_objectives_count": topic_objective_missing,
            "missing_learning_objectives_rate_pct": ratio(topic_objective_missing, len(topics)),
            "missing_common_mistakes_count": topic_mistake_missing,
            "missing_common_mistakes_rate_pct": ratio(topic_mistake_missing, len(topics)),
        },
        "explanation_quality": {
            "missing_summary_count": explanation_summary_missing,
            "missing_summary_rate_pct": ratio(explanation_summary_missing, len(explanations)),
        },
        "top_method_tags": [{"tag": k, "count": v} for k, v in top_tag_counter.most_common(20)],
    }
    (out_dir / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"problem_count": len(problems), "report_path": "artifacts/quality/report.json"}, ensure_ascii=False))


if __name__ == "__main__":
    main()
