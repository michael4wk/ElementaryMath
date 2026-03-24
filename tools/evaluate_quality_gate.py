#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple


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


def write_jsonl(path: Path, row: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def parse_rule_source(source: str) -> Tuple[str, str]:
    if "." not in source:
        return source, ""
    top, section = source.split(".", 1)
    return top.strip(), section.strip()


def pick_metric(metric: str, source: str, quality: dict, validation: dict) -> Optional[float]:
    top, section = parse_rule_source(source)
    value = None
    if top == "quality":
        block = quality.get(section, {}) if section else quality
        value = block.get(metric)
    elif top == "validation":
        block = validation.get(section, {}) if section else validation
        value = block.get(metric)
    else:
        value = None
    if value is None:
        return None
    try:
        return float(value)
    except Exception:
        return None


def compare(value: Optional[float], op: str, threshold: float) -> bool:
    if value is None:
        return False
    if op == ">=":
        return value >= threshold
    if op == "<=":
        return value <= threshold
    if op == ">":
        return value > threshold
    if op == "<":
        return value < threshold
    if op == "==":
        return abs(value - threshold) < 1e-9
    return False


def evaluate_rules(rules: List[dict], quality: dict, validation: dict) -> List[dict]:
    out: List[dict] = []
    for rule in rules:
        metric = str(rule.get("metric", "")).strip()
        op = str(rule.get("operator", "")).strip()
        source = str(rule.get("source", "")).strip()
        threshold = float(rule.get("threshold", 0.0))
        value = pick_metric(metric, source, quality, validation)
        passed = compare(value, op, threshold)
        out.append(
            {
                "metric": metric,
                "source": source,
                "operator": op,
                "threshold": threshold,
                "value": value,
                "passed": passed,
            }
        )
    return out


def regression_result(current: dict, previous: dict, enabled: bool, max_drop_pct: float) -> dict:
    if not enabled:
        return {"enabled": False, "passed": True, "details": []}
    if not previous:
        return {"enabled": True, "passed": True, "details": [], "reason": "no_previous_record"}
    metrics = [
        "answer_analysis_consistency_rate_pct",
        "learning_objectives_coverage_pct",
        "common_mistakes_coverage_pct",
        "method_tags_coverage_pct",
    ]
    details: List[dict] = []
    passed = True
    for metric in metrics:
        current_value = current.get(metric)
        previous_value = previous.get(metric)
        if current_value is None or previous_value is None:
            continue
        drop = round(float(previous_value) - float(current_value), 2)
        metric_passed = drop <= max_drop_pct
        if not metric_passed:
            passed = False
        details.append(
            {
                "metric": metric,
                "previous": float(previous_value),
                "current": float(current_value),
                "drop_pct": drop,
                "max_drop_pct": max_drop_pct,
                "passed": metric_passed,
            }
        )
    return {"enabled": True, "passed": passed, "details": details}


def collect_current_metrics(quality: dict, validation: dict) -> dict:
    problem = quality.get("problem_quality", {})
    topic = quality.get("topic_quality", {})
    completeness = validation.get("completeness", {})
    consistency = validation.get("consistency", {})
    traceability = validation.get("traceability", {})
    return {
        "answer_analysis_consistency_rate_pct": consistency.get("answer_analysis_consistency_rate_pct"),
        "empty_analysis_rate_pct": problem.get("empty_analysis_rate_pct"),
        "missing_common_mistakes_rate_pct": topic.get("missing_common_mistakes_rate_pct"),
        "missing_grade_band_rate_pct": problem.get("missing_grade_band_rate_pct"),
        "missing_difficulty_rate_pct": problem.get("missing_difficulty_rate_pct"),
        "missing_learning_objectives_rate_pct": topic.get("missing_learning_objectives_rate_pct"),
        "learning_objectives_coverage_pct": completeness.get("learning_objectives_coverage_pct"),
        "common_mistakes_coverage_pct": completeness.get("common_mistakes_coverage_pct"),
        "method_tags_coverage_pct": completeness.get("method_tags_coverage_pct"),
        "source_ref_coverage_pct": traceability.get("source_ref_coverage_pct"),
    }


def latest_history(history_rows: List[dict], profile: str) -> dict:
    for row in reversed(history_rows):
        if str(row.get("profile", "")).strip() == profile:
            return row
    return {}


def build_blockers(hard_results: List[dict], regression: dict) -> List[dict]:
    blockers: List[dict] = []
    for item in hard_results:
        if not bool(item.get("passed", False)):
            blockers.append(
                {
                    "code": "hard_rule_failed",
                    "metric": item.get("metric"),
                    "source": item.get("source"),
                    "operator": item.get("operator"),
                    "threshold": item.get("threshold"),
                    "value": item.get("value"),
                }
            )
    if regression.get("enabled") and not regression.get("passed", True):
        blockers.append({"code": "regression_failed", "details": regression.get("details", [])})
    return blockers


def build_warnings(soft_results: List[dict]) -> List[dict]:
    warnings: List[dict] = []
    for item in soft_results:
        if not bool(item.get("passed", False)):
            warnings.append(
                {
                    "code": "soft_rule_failed",
                    "metric": item.get("metric"),
                    "source": item.get("source"),
                    "operator": item.get("operator"),
                    "threshold": item.get("threshold"),
                    "value": item.get("value"),
                }
            )
    return warnings


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", type=str, default=".")
    parser.add_argument("--profile", type=str, default="")
    args = parser.parse_args()

    project_root = Path(args.project_root).resolve()
    quality_dir = project_root / "artifacts" / "quality"
    quality_dir.mkdir(parents=True, exist_ok=True)

    profile_conf = read_json(project_root / "config" / "quality_gate_profiles.json")
    default_profile = str(profile_conf.get("default_profile", "staging")).strip() or "staging"
    profile = str(args.profile).strip() or default_profile
    profiles = profile_conf.get("profiles", {})
    selected = profiles.get(profile, {})
    if not selected:
        raise SystemExit(f"profile not found: {profile}")

    quality_report = read_json(quality_dir / "report.json")
    validation_report = read_json(quality_dir / "validation.json")
    history_rows = read_jsonl(quality_dir / "gate_history.jsonl")

    hard_rules = selected.get("hard_rules", [])
    soft_rules = selected.get("soft_rules", [])
    hard_results = evaluate_rules(hard_rules, quality_report, validation_report)
    soft_results = evaluate_rules(soft_rules, quality_report, validation_report)

    current_metrics = collect_current_metrics(quality_report, validation_report)
    previous = latest_history(history_rows, profile).get("metrics", {})
    regression_conf = selected.get("regression", {})
    regression = regression_result(
        current=current_metrics,
        previous=previous if isinstance(previous, dict) else {},
        enabled=bool(regression_conf.get("enabled", False)),
        max_drop_pct=float(regression_conf.get("max_drop_pct", 0.0)),
    )

    blockers = build_blockers(hard_results, regression)
    warnings = build_warnings(soft_results)
    report = {
        "profile": profile,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "can_release": len(blockers) == 0,
        "blockers": blockers,
        "warnings": warnings,
        "hard_results": hard_results,
        "soft_results": soft_results,
        "regression": regression,
        "metrics": current_metrics,
    }

    (quality_dir / "gate_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    write_jsonl(
        quality_dir / "gate_history.jsonl",
        {
            "profile": profile,
            "generated_at": report["generated_at"],
            "can_release": report["can_release"],
            "metrics": current_metrics,
            "blocker_count": len(blockers),
            "warning_count": len(warnings),
        },
    )
    print(
        json.dumps(
            {
                "report_path": "artifacts/quality/gate_report.json",
                "history_path": "artifacts/quality/gate_history.jsonl",
                "profile": profile,
                "can_release": report["can_release"],
                "blocker_count": len(blockers),
                "warning_count": len(warnings),
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
