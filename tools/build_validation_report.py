#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import List

from quality_rules import classify_consistency_conflicts, semantic_consistency_confidence


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


def has_source_ref(row: dict) -> bool:
    ref = row.get("source_ref")
    if isinstance(ref, str):
        return bool(ref.strip())
    if isinstance(ref, dict):
        return bool(str(ref.get("asset_id", "")).strip()) or bool(str(ref.get("file_path", "")).strip()) or bool(str(ref.get("text_path", "")).strip())
    return False


def classify_problem_issue(row: dict) -> List[dict]:
    issues: List[dict] = []
    stem = str(row.get("stem", "")).strip()
    answer = str(row.get("answer", "")).strip()
    steps = row.get("analysis_steps", [])
    step_rows = steps if isinstance(steps, list) else []
    confidence = semantic_consistency_confidence(stem=stem, answer=answer, analysis_steps=step_rows)
    conflicts = classify_consistency_conflicts(stem=stem, answer=answer, analysis_steps=step_rows)
    for code in conflicts:
        severity = "P2"
        reason = "rule_detected"
        if code in ("answer_analysis_missing",):
            severity = "P0"
            reason = "extraction_missing_both"
        elif code in ("answer_missing",):
            severity = "P1"
            reason = "extraction_missing_answer"
        elif code in ("analysis_missing",):
            severity = "P1"
            reason = "extraction_missing_analysis"
        elif code in ("answer_formula_placeholder",):
            severity = "P2"
            reason = "formula_placeholder"
        elif code in ("number_mismatch", "unit_mismatch", "semantic_weak_overlap"):
            severity = "P1"
        issues.append(
            {
                "severity": severity,
                "issue_type": "consistency",
                "conflict_type_code": code,
                "missing_reason_code": reason,
                "semantic_confidence_pct": confidence,
            }
        )
    if not has_source_ref(row):
        issues.append(
            {
                "severity": "P0",
                "issue_type": "traceability",
                "conflict_type_code": "source_ref_missing",
                "missing_reason_code": "source_ref_missing",
                "semantic_confidence_pct": confidence,
            }
        )
    return issues


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
    semantic_confidence_total = 0.0
    issue_rows: List[dict] = []
    severity_counter = Counter()
    issue_type_counter = Counter()
    conflict_counter = Counter()
    missing_reason_counter = Counter()
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
        semantic_confidence_total += semantic_consistency_confidence(
            stem=str(p.get("stem", "")).strip(),
            answer=answer,
            analysis_steps=steps if isinstance(steps, list) else [],
        )
        consistency_checks.append({"problem_id": p.get("problem_id", ""), "ok": ok})
        issues = classify_problem_issue(p)
        for issue in issues:
            issue_row = {
                "issue_id": f"issue_{p.get('problem_id', '')}_{issue.get('conflict_type_code', '')}",
                "severity": issue.get("severity", ""),
                "issue_type": issue.get("issue_type", ""),
                "conflict_type_code": issue.get("conflict_type_code", ""),
                "missing_reason_code": issue.get("missing_reason_code", ""),
                "semantic_confidence_pct": issue.get("semantic_confidence_pct", 0.0),
                "topic_id": p.get("topic_id", ""),
                "problem_id": p.get("problem_id", ""),
                "source_ref": p.get("source_ref", {}),
            }
            issue_rows.append(issue_row)
            severity_counter[issue_row["severity"]] += 1
            issue_type_counter[issue_row["issue_type"]] += 1
            conflict_counter[issue_row["conflict_type_code"]] += 1
            missing_reason_counter[issue_row["missing_reason_code"]] += 1

    consistency = {
        "checked_problem_count": len(problems),
        "answer_present_rate_pct": ratio(answer_present, len(problems)),
        "analysis_present_rate_pct": ratio(analysis_present, len(problems)),
        "answer_analysis_consistency_rate_pct": ratio(answer_analysis_consistent, len(problems)),
        "semantic_consistency_confidence_avg_pct": round(semantic_confidence_total / max(1, len(problems)), 2),
        "logic_consistent_ready": bool(ratio(answer_analysis_consistent, len(problems)) >= 70.0),
    }

    topic_source_ok = sum(1 for t in topics if has_source_ref(t))
    concept_source_ok = sum(1 for c in concepts if has_source_ref(c))
    problem_source_ok = sum(1 for p in problems if has_source_ref(p))
    explanation_source_ok = sum(1 for e in explanations if has_source_ref(e))
    total_objects = len(topics) + len(concepts) + len(problems) + len(explanations)
    source_ref_ready_count = topic_source_ok + concept_source_ok + problem_source_ok + explanation_source_ok
    traceability = {
        "topic_source_ref_coverage_pct": ratio(topic_source_ok, len(topics)),
        "concept_source_ref_coverage_pct": ratio(concept_source_ok, len(concepts)),
        "problem_source_ref_coverage_pct": ratio(problem_source_ok, len(problems)),
        "explanation_source_ref_coverage_pct": ratio(explanation_source_ok, len(explanations)),
        "source_ref_coverage_pct": ratio(source_ref_ready_count, total_objects),
        "traceability_ready": bool(total_objects > 0 and ratio(source_ref_ready_count, total_objects) >= 99.0),
    }

    issues = {
        "total": len(issue_rows),
        "severity_distribution": dict(severity_counter),
        "issue_type_distribution": dict(issue_type_counter),
        "conflict_type_distribution": dict(conflict_counter),
        "missing_reason_distribution": dict(missing_reason_counter),
    }

    report = {"completeness": completeness, "consistency": consistency, "traceability": traceability, "issues": issues}
    (quality_dir / "validation.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    issue_path = quality_dir / "issues.jsonl"
    with issue_path.open("w", encoding="utf-8") as f:
        for row in issue_rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(json.dumps({"report_path": "artifacts/quality/validation.json"}, ensure_ascii=False))


if __name__ == "__main__":
    main()
