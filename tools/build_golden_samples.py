#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from collections import defaultdict
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


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", type=str, default=".")
    parser.add_argument("--max-per-bucket", type=int, default=3)
    args = parser.parse_args()

    root = Path(args.project_root).resolve()
    curated_dir = root / "artifacts" / "curated"
    quality_dir = root / "artifacts" / "quality"
    quality_dir.mkdir(parents=True, exist_ok=True)

    problems = read_jsonl(curated_dir / "problems.jsonl")
    buckets = defaultdict(list)
    for row in problems:
        grade = str(row.get("grade_band", "")).strip() or "unknown"
        tags = row.get("method_tags", [])
        method = str(tags[0]).strip() if isinstance(tags, list) and tags and str(tags[0]).strip() else "unknown"
        key = f"{grade}::{method}"
        if len(buckets[key]) >= max(1, args.max_per_bucket):
            continue
        buckets[key].append(
            {
                "topic_id": row.get("topic_id", ""),
                "problem_id": row.get("problem_id", ""),
                "grade_band": grade,
                "method_tag": method,
                "stem": row.get("stem", ""),
                "answer": row.get("answer", ""),
                "analysis_steps": row.get("analysis_steps", []),
                "source_ref": row.get("source_ref", {}),
            }
        )
    samples: List[dict] = []
    for key in sorted(buckets.keys()):
        samples.extend(buckets[key])

    out_path = quality_dir / "golden_samples.jsonl"
    with out_path.open("w", encoding="utf-8") as f:
        for row in samples:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    summary = {
        "sample_total": len(samples),
        "bucket_total": len(buckets),
        "max_per_bucket": args.max_per_bucket,
        "output_path": "artifacts/quality/golden_samples.jsonl",
    }
    (quality_dir / "golden_samples_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
