#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
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


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", type=str, default=".")
    parser.add_argument("--profile", type=str, default="staging")
    args = parser.parse_args()

    root = Path(args.project_root).resolve()
    quality_dir = root / "artifacts" / "quality"
    history = read_jsonl(quality_dir / "gate_history.jsonl")
    report = read_json(quality_dir / "gate_report.json")
    profile = str(args.profile).strip() or "staging"
    profile_rows = [x for x in history if str(x.get("profile", "")).strip() == profile]

    previous = profile_rows[-2] if len(profile_rows) >= 2 else {}
    current = profile_rows[-1] if len(profile_rows) >= 1 else {}
    previous_metrics = previous.get("metrics", {}) if isinstance(previous.get("metrics", {}), dict) else {}
    current_metrics = current.get("metrics", {}) if isinstance(current.get("metrics", {}), dict) else {}

    diff_metrics = {}
    all_keys = sorted(set(list(previous_metrics.keys()) + list(current_metrics.keys())))
    for key in all_keys:
        pv = previous_metrics.get(key)
        cv = current_metrics.get(key)
        if pv is None or cv is None:
            continue
        try:
            diff_metrics[key] = round(float(cv) - float(pv), 2)
        except Exception:
            continue

    blocker_count = len(report.get("blockers", [])) if isinstance(report.get("blockers", []), list) else 0
    warning_count = len(report.get("warnings", [])) if isinstance(report.get("warnings", []), list) else 0
    rollback_recommended = (not bool(report.get("can_release", False))) or blocker_count > int(previous.get("blocker_count", 0) or 0)

    out = {
        "profile": profile,
        "has_previous_cycle": bool(previous),
        "current_can_release": bool(report.get("can_release", False)),
        "current_blocker_count": blocker_count,
        "current_warning_count": warning_count,
        "previous_blocker_count": int(previous.get("blocker_count", 0) or 0),
        "previous_warning_count": int(previous.get("warning_count", 0) or 0),
        "metric_delta_pct": diff_metrics,
        "rollback_recommended": rollback_recommended,
        "rollback_reason": "gate_blocked_or_risk_increase" if rollback_recommended else "stable",
    }
    (quality_dir / "release_diff.json").write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"release_diff_path": "artifacts/quality/release_diff.json", "rollback_recommended": rollback_recommended}, ensure_ascii=False))


if __name__ == "__main__":
    main()
