#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import List


def read_json(path: Path) -> dict:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


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


def top_pairs(counter_map: dict[str, Counter], topn: int = 8) -> dict:
    out = {}
    for key, cnt in counter_map.items():
        out[key] = [{"name": k, "count": v} for k, v in cnt.most_common(topn)]
    return out


def build_review_pool(issues: List[dict], problems: dict[str, dict], limit: int = 300) -> List[dict]:
    rows: List[dict] = []
    seen = set()
    for issue in issues:
        pid = str(issue.get("problem_id", "")).strip()
        if not pid or pid in seen:
            continue
        severity = str(issue.get("severity", "")).strip()
        confidence = float(issue.get("semantic_confidence_pct", 0.0) or 0.0)
        if severity in ("P0", "P1") or confidence < 40.0:
            p = problems.get(pid, {})
            rows.append(
                {
                    "problem_id": pid,
                    "topic_id": issue.get("topic_id", ""),
                    "severity": severity,
                    "semantic_confidence_pct": confidence,
                    "conflict_type_code": issue.get("conflict_type_code", ""),
                    "missing_reason_code": issue.get("missing_reason_code", ""),
                    "stem": p.get("stem", ""),
                    "answer": p.get("answer", ""),
                    "analysis_steps": p.get("analysis_steps", []),
                    "status": "pending_review",
                    "review_action": "",
                }
            )
            seen.add(pid)
        if len(rows) >= limit:
            break
    return rows


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", type=str, default=".")
    args = parser.parse_args()

    root = Path(args.project_root).resolve()
    quality_dir = root / "artifacts" / "quality"
    curated_dir = root / "artifacts" / "curated"
    quality_dir.mkdir(parents=True, exist_ok=True)

    issues = read_jsonl(quality_dir / "issues.jsonl")
    problems = read_jsonl(curated_dir / "problems.jsonl")
    problem_map = {str(p.get("problem_id", "")).strip(): p for p in problems}
    gate = read_json(quality_dir / "gate_report.json")
    validation = read_json(quality_dir / "validation.json")
    history = read_jsonl(quality_dir / "gate_history.jsonl")

    grade_hotspot = defaultdict(Counter)
    method_hotspot = defaultdict(Counter)
    topic_hotspot = Counter()
    for issue in issues:
        code = str(issue.get("conflict_type_code", "")).strip()
        pid = str(issue.get("problem_id", "")).strip()
        problem = problem_map.get(pid, {})
        grade = str(problem.get("grade_band", "")).strip() or "unknown"
        tags = problem.get("method_tags", [])
        grade_hotspot[code][grade] += 1
        if isinstance(tags, list):
            for t in tags[:3]:
                method_hotspot[code][str(t).strip() or "unknown"] += 1
        topic_hotspot[str(issue.get("topic_id", "")).strip() or "unknown"] += 1

    review_pool = build_review_pool(issues, problem_map, limit=300)
    review_pool_path = quality_dir / "review_pool.jsonl"
    with review_pool_path.open("w", encoding="utf-8") as f:
        for row in review_pool:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    rollback_recommended = False
    if not bool(gate.get("can_release", False)):
        rollback_recommended = True
    if len(history) >= 2:
        prev = history[-2]
        curr = history[-1]
        if int(curr.get("blocker_count", 0) or 0) > int(prev.get("blocker_count", 0) or 0):
            rollback_recommended = True

    ops_report = {
        "summary": {
            "issue_total": len(issues),
            "review_pool_total": len(review_pool),
            "semantic_confidence_avg_pct": validation.get("consistency", {}).get("semantic_consistency_confidence_avg_pct", 0.0),
            "gate_can_release": bool(gate.get("can_release", False)),
            "rollback_recommended": rollback_recommended,
        },
        "missing_hotspots": {
            "by_grade": top_pairs(grade_hotspot, topn=8),
            "by_method_tag": top_pairs(method_hotspot, topn=8),
            "by_topic": [{"topic_id": k, "count": v} for k, v in topic_hotspot.most_common(20)],
        },
    }
    (quality_dir / "ops_report.json").write_text(json.dumps(ops_report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        json.dumps(
            {
                "ops_report_path": "artifacts/quality/ops_report.json",
                "review_pool_path": "artifacts/quality/review_pool.jsonl",
                "review_pool_total": len(review_pool),
                "rollback_recommended": rollback_recommended,
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
