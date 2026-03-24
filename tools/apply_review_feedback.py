#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
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


def write_json(path: Path, row: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(row, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", type=str, default=".")
    args = parser.parse_args()

    root = Path(args.project_root).resolve()
    quality_dir = root / "artifacts" / "quality"
    feedback_path = quality_dir / "review_feedback.jsonl"
    pool_path = quality_dir / "review_pool.jsonl"
    backflow_path = quality_dir / "review_backflow.json"
    learned_path = root / "config" / "common_mistake_templates.learned.json"

    pool_rows = read_jsonl(pool_path)
    feedback_rows = read_jsonl(feedback_path)
    feedback_map = {str(x.get("problem_id", "")).strip(): x for x in feedback_rows if str(x.get("problem_id", "")).strip()}
    action_counter = Counter()
    topic_counter = Counter()
    learned_by_keyword = defaultdict(list)

    applied_rows: List[dict] = []
    for row in pool_rows:
        pid = str(row.get("problem_id", "")).strip()
        fb = feedback_map.get(pid)
        if not fb:
            applied_rows.append(row)
            continue
        action = str(fb.get("review_action", "")).strip()
        action_counter[action or "none"] += 1
        topic_id = str(row.get("topic_id", "")).strip()
        if topic_id:
            topic_counter[topic_id] += 1
        new_row = dict(row)
        new_row["status"] = "reviewed"
        new_row["review_action"] = action
        new_row["review_comment"] = str(fb.get("review_comment", "")).strip()
        new_row["fixed_analysis_steps"] = fb.get("fixed_analysis_steps", row.get("analysis_steps", []))
        new_row["fixed_common_mistake"] = str(fb.get("fixed_common_mistake", "")).strip()
        keyword = str(fb.get("keyword", "")).strip()
        if keyword and new_row["fixed_common_mistake"]:
            learned_by_keyword[keyword].append(new_row["fixed_common_mistake"])
        applied_rows.append(new_row)

    with pool_path.open("w", encoding="utf-8") as f:
        for row in applied_rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    learned_templates = {
        "keyword_templates": [
            {"keyword": k, "mistakes": sorted(list({x for x in v if x}))[:20]} for k, v in learned_by_keyword.items() if v
        ]
    }
    if learned_templates["keyword_templates"]:
        write_json(learned_path, learned_templates)

    backflow = {
        "feedback_total": len(feedback_rows),
        "reviewed_total": sum(1 for x in applied_rows if str(x.get("status", "")).strip() == "reviewed"),
        "action_distribution": dict(action_counter),
        "top_topics": [{"topic_id": k, "count": v} for k, v in topic_counter.most_common(20)],
        "learned_template_file": str(learned_path.relative_to(root)) if learned_templates["keyword_templates"] else "",
    }
    write_json(backflow_path, backflow)
    print(
        json.dumps(
            {
                "backflow_path": "artifacts/quality/review_backflow.json",
                "reviewed_total": backflow["reviewed_total"],
                "learned_template_file": backflow["learned_template_file"],
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
