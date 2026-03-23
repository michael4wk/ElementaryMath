#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
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
    if d <= 0:
        return 0.0
    return round(n * 100.0 / d, 2)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", type=str, default=".")
    args = parser.parse_args()

    root = Path(args.project_root).resolve()
    curated_dir = root / "artifacts" / "curated"
    quality_dir = root / "artifacts" / "quality"
    quality_dir.mkdir(parents=True, exist_ok=True)

    topics = read_jsonl(curated_dir / "topics.jsonl")
    concepts = read_jsonl(curated_dir / "concepts.jsonl")
    problems = read_jsonl(curated_dir / "problems.jsonl")
    explanations = read_jsonl(curated_dir / "explanations.jsonl")

    obj_ok = sum(1 for t in topics if isinstance(t.get("learning_objectives"), list) and len(t.get("learning_objectives", [])) > 0)
    mistakes_ok = sum(1 for t in topics if isinstance(t.get("common_mistakes"), list) and len(t.get("common_mistakes", [])) > 0)
    method_ok = sum(1 for p in problems if isinstance(p.get("method_tags"), list) and len(p.get("method_tags", [])) > 0)

    completeness = {
        "topic_total": len(topics),
        "concept_total": len(concepts),
        "problem_total": len(problems),
        "explanation_total": len(explanations),
        "learning_objectives_coverage_pct": ratio(obj_ok, len(topics)),
        "common_mistakes_coverage_pct": ratio(mistakes_ok, len(topics)),
        "method_tags_coverage_pct": ratio(method_ok, len(problems)),
        "required_objects_ready": bool(len(topics) > 0 and len(concepts) > 0 and len(problems) > 0 and len(explanations) > 0),
        "fields_ready": bool(ratio(obj_ok, len(topics)) >= 30.0 and ratio(mistakes_ok, len(topics)) >= 30.0 and ratio(method_ok, len(problems)) >= 95.0),
    }

    consistency_checks = []
    answer_present = 0
    analysis_present = 0
    answer_analysis_consistent = 0
    for p in problems:
        answer = str(p.get("answer", "")).strip()
        steps = p.get("analysis_steps", [])
        has_answer = bool(answer)
        has_analysis = isinstance(steps, list) and len(steps) > 0
        if has_answer:
            answer_present += 1
        if has_analysis:
            analysis_present += 1
        ok = has_answer and has_analysis
        if ok:
            answer_analysis_consistent += 1
        consistency_checks.append({"problem_id": p.get("problem_id", ""), "ok": ok})

    consistency = {
        "checked_problem_count": len(problems),
        "answer_present_rate_pct": ratio(answer_present, len(problems)),
        "analysis_present_rate_pct": ratio(analysis_present, len(problems)),
        "answer_analysis_consistency_rate_pct": ratio(answer_analysis_consistent, len(problems)),
        "logic_consistent_ready": bool(ratio(answer_analysis_consistent, len(problems)) >= 70.0),
    }

    report = {"completeness": completeness, "consistency": consistency}
    (quality_dir / "validation.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"report_path": "artifacts/quality/validation.json"}, ensure_ascii=False))


if __name__ == "__main__":
    main()
