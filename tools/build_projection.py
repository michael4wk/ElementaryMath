#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Dict, Iterable, List


def read_json(path: Path) -> dict:
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


def write_jsonl(path: Path, rows: Iterable[dict]) -> None:
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def project_row(row: dict, hide_fields: List[str]) -> dict:
    out = dict(row)
    for field in hide_fields:
        if field in out:
            out[field] = None
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", type=str, default=".")
    args = parser.parse_args()

    project_root = Path(args.project_root).resolve()
    rules = read_json(project_root / "config" / "projection_rules.json")
    curated_dir = project_root / "artifacts" / "curated"
    serving_dir = project_root / "artifacts" / "serving"
    serving_dir.mkdir(parents=True, exist_ok=True)

    topics = read_jsonl(curated_dir / "topics.jsonl")
    problems = read_jsonl(curated_dir / "problems.jsonl")
    explanations = read_jsonl(curated_dir / "explanations.jsonl")

    projections: Dict[str, List[str]] = {
        audience: conf.get("hide_fields", [])
        for audience, conf in rules.get("audience_projection", {}).items()
    }
    total_written = 0
    for audience, hide_fields in projections.items():
        p_topics = [project_row(row, hide_fields) for row in topics]
        p_problems = [project_row(row, hide_fields) for row in problems]
        p_explanations = [project_row(row, hide_fields) for row in explanations]
        write_jsonl(serving_dir / f"topics_{audience}.jsonl", p_topics)
        write_jsonl(serving_dir / f"problems_{audience}.jsonl", p_problems)
        write_jsonl(serving_dir / f"explanations_{audience}.jsonl", p_explanations)
        total_written += len(p_topics) + len(p_problems) + len(p_explanations)

    summary = {
        "audiences": sorted(list(projections.keys())),
        "topic_count": len(topics),
        "problem_count": len(problems),
        "explanation_count": len(explanations),
        "total_written_rows": total_written,
    }
    (serving_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
