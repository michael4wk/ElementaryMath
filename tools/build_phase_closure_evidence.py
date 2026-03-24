#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path


def read_json(path: Path) -> dict:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", type=str, default=".")
    args = parser.parse_args()

    root = Path(args.project_root).resolve()
    quality_dir = root / "artifacts" / "quality"
    quality_dir.mkdir(parents=True, exist_ok=True)

    quality = read_json(quality_dir / "report.json")
    validation = read_json(quality_dir / "validation.json")
    gate = read_json(quality_dir / "gate_report.json")
    release_diff = read_json(quality_dir / "release_diff.json")
    golden_summary = read_json(quality_dir / "golden_samples_summary.json")
    ops_report = read_json(quality_dir / "ops_report.json")

    topic_quality = quality.get("topic_quality", {})
    problem_quality = quality.get("problem_quality", {})
    consistency = validation.get("consistency", {})
    baseline = {
        "frozen_at": datetime.now(timezone.utc).isoformat(),
        "baseline_origin": "phase_start_acceptance_snapshot",
        "initial": {
            "answer_analysis_consistency_rate_pct": 79.51,
            "empty_analysis_rate_pct": 19.26,
            "missing_common_mistakes_rate_pct": 35.75,
        },
        "current": {
            "answer_analysis_consistency_rate_pct": consistency.get("answer_analysis_consistency_rate_pct", 0.0),
            "empty_analysis_rate_pct": problem_quality.get("empty_analysis_rate_pct", 0.0),
            "missing_common_mistakes_rate_pct": topic_quality.get("missing_common_mistakes_rate_pct", 0.0),
            "source_ref_coverage_pct": validation.get("traceability", {}).get("source_ref_coverage_pct", 0.0),
        },
        "gate": {
            "can_release": bool(gate.get("can_release", False)),
            "blocker_count": len(gate.get("blockers", [])) if isinstance(gate.get("blockers", []), list) else 0,
            "warning_count": len(gate.get("warnings", [])) if isinstance(gate.get("warnings", []), list) else 0,
        },
        "golden_samples": golden_summary,
    }
    (quality_dir / "baseline_freeze.json").write_text(json.dumps(baseline, ensure_ascii=False, indent=2), encoding="utf-8")

    hotspot_done = bool(problem_quality.get("empty_analysis_rate_pct", 100.0) <= 8.0)
    closure = {
        "generated_at": baseline["frozen_at"],
        "hotspot_fix_status": "completed" if hotspot_done else "in_progress",
        "hotspot_fix_reason": "empty_analysis_rate_pct_reached_threshold" if hotspot_done else "threshold_not_reached",
        "gate_can_release": baseline["gate"]["can_release"],
        "rollback_recommended": bool(release_diff.get("rollback_recommended", False)),
        "top_missing_hotspots": ops_report.get("missing_hotspots", {}).get("by_topic", [])[:10],
    }
    (quality_dir / "hotspot_fix_report.json").write_text(json.dumps(closure, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"baseline_path": "artifacts/quality/baseline_freeze.json", "hotspot_fix_path": "artifacts/quality/hotspot_fix_report.json", "hotspot_fix_status": closure["hotspot_fix_status"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
