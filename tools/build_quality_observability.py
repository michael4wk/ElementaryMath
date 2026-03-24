#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import datetime, timezone
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


def metric_change(curr: float, prev: float) -> float:
    return round(float(curr) - float(prev), 2)


def build_trend(history: List[dict]) -> dict:
    rows = history[-30:]
    points = []
    for row in rows:
        metrics = row.get("metrics", {}) if isinstance(row.get("metrics", {}), dict) else {}
        points.append(
            {
                "ts": row.get("generated_at", ""),
                "can_release": bool(row.get("can_release", False)),
                "blocker_count": int(row.get("blocker_count", 0) or 0),
                "warning_count": int(row.get("warning_count", 0) or 0),
                "answer_analysis_consistency_rate_pct": float(metrics.get("answer_analysis_consistency_rate_pct", 0.0) or 0.0),
                "empty_analysis_rate_pct": float(metrics.get("empty_analysis_rate_pct", 0.0) or 0.0),
                "missing_common_mistakes_rate_pct": float(metrics.get("missing_common_mistakes_rate_pct", 0.0) or 0.0),
            }
        )
    stable_cycles = 0
    for row in reversed(points):
        if row["can_release"]:
            stable_cycles += 1
        else:
            break
    return {"points": points, "stable_release_cycles": stable_cycles}


def build_alerts(gate: dict, trend: dict, validation: dict) -> dict:
    alerts = []
    blockers = gate.get("blockers", []) if isinstance(gate.get("blockers", []), list) else []
    warnings = gate.get("warnings", []) if isinstance(gate.get("warnings", []), list) else []
    if blockers:
        alerts.append({"level": "critical", "code": "gate_blocked", "detail": f"blockers={len(blockers)}"})
    if warnings:
        alerts.append({"level": "warning", "code": "gate_warning", "detail": f"warnings={len(warnings)}"})
    points = trend.get("points", [])
    if len(points) >= 2:
        prev = points[-2]
        curr = points[-1]
        if curr.get("answer_analysis_consistency_rate_pct", 0.0) < prev.get("answer_analysis_consistency_rate_pct", 0.0):
            alerts.append(
                {
                    "level": "warning",
                    "code": "consistency_regression",
                    "detail": metric_change(curr["answer_analysis_consistency_rate_pct"], prev["answer_analysis_consistency_rate_pct"]),
                }
            )
        if curr.get("empty_analysis_rate_pct", 0.0) > prev.get("empty_analysis_rate_pct", 0.0):
            alerts.append(
                {
                    "level": "warning",
                    "code": "analysis_missing_rise",
                    "detail": metric_change(curr["empty_analysis_rate_pct"], prev["empty_analysis_rate_pct"]),
                }
            )
    semantic_avg = float(validation.get("consistency", {}).get("semantic_consistency_confidence_avg_pct", 0.0) or 0.0)
    if semantic_avg < 45.0:
        alerts.append({"level": "warning", "code": "semantic_confidence_low", "detail": semantic_avg})
    return {"generated_at": datetime.now(timezone.utc).isoformat(), "alert_count": len(alerts), "alerts": alerts}


def build_repair_tracking(issues: List[dict], review_pool: List[dict], backflow: dict) -> dict:
    severity_counter = Counter([str(x.get("severity", "")).strip() for x in issues])
    reviewed = [x for x in review_pool if str(x.get("status", "")).strip() == "reviewed"]
    pending = [x for x in review_pool if str(x.get("status", "")).strip() != "reviewed"]
    reviewed_total = len(reviewed)
    pending_total = len(pending)
    close_rate = round(reviewed_total * 100.0 / max(1, reviewed_total + pending_total), 2)
    return {
        "issue_total": len(issues),
        "severity_distribution": dict(severity_counter),
        "review_pool_total": len(review_pool),
        "reviewed_total": reviewed_total,
        "pending_total": pending_total,
        "review_close_rate_pct": close_rate,
        "feedback_total": int(backflow.get("feedback_total", 0) or 0),
        "reviewed_feedback_total": int(backflow.get("reviewed_total", 0) or 0),
        "action_distribution": backflow.get("action_distribution", {}),
    }


def write_markdown_reports(ops_dir: Path, trend: dict, alerts: dict, repair: dict) -> None:
    trend_path = ops_dir / "quality_trend.md"
    points = trend.get("points", [])
    latest = points[-1] if points else {}
    trend_lines = [
        "# 质量趋势看板",
        "",
        f"- 最新时间: {latest.get('ts', '')}",
        f"- 连续可放行周期: {trend.get('stable_release_cycles', 0)}",
        f"- 当前阻断数: {latest.get('blocker_count', 0)}",
        f"- 当前告警数: {latest.get('warning_count', 0)}",
        f"- 一致率: {latest.get('answer_analysis_consistency_rate_pct', 0.0)}%",
        f"- 解析缺失率: {latest.get('empty_analysis_rate_pct', 0.0)}%",
        f"- 易错点缺失率: {latest.get('missing_common_mistakes_rate_pct', 0.0)}%",
    ]
    trend_path.write_text("\n".join(trend_lines) + "\n", encoding="utf-8")

    alerts_path = ops_dir / "quality_alerts.md"
    alert_lines = ["# 质量告警", "", f"- 告警时间: {alerts.get('generated_at', '')}", f"- 告警数量: {alerts.get('alert_count', 0)}", ""]
    rows = alerts.get("alerts", [])
    if not rows:
        alert_lines.append("- 无告警")
    else:
        for row in rows:
            alert_lines.append(f"- [{row.get('level', 'info')}] {row.get('code', '')}: {row.get('detail', '')}")
    alerts_path.write_text("\n".join(alert_lines) + "\n", encoding="utf-8")

    review_path = ops_dir / "monthly_quality_review.md"
    review_lines = [
        "# 月度质量复盘（模板）",
        "",
        f"- 生成时间: {datetime.now(timezone.utc).isoformat()}",
        f"- 当前一致率: {latest.get('answer_analysis_consistency_rate_pct', 0.0)}%",
        f"- 当前解析缺失率: {latest.get('empty_analysis_rate_pct', 0.0)}%",
        f"- 当前易错点缺失率: {latest.get('missing_common_mistakes_rate_pct', 0.0)}%",
        f"- 当前可放行连续周期: {trend.get('stable_release_cycles', 0)}",
        f"- 复核关闭率: {repair.get('review_close_rate_pct', 0.0)}%",
        "",
        "## 本月关键问题",
        "- ",
        "## 根因分析",
        "- ",
        "## 修复动作",
        "- ",
        "## 下月计划",
        "- ",
    ]
    review_path.write_text("\n".join(review_lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", type=str, default=".")
    args = parser.parse_args()

    root = Path(args.project_root).resolve()
    quality_dir = root / "artifacts" / "quality"
    ops_dir = root / "artifacts" / "ops"
    ops_dir.mkdir(parents=True, exist_ok=True)

    history = read_jsonl(quality_dir / "gate_history.jsonl")
    gate = read_json(quality_dir / "gate_report.json")
    validation = read_json(quality_dir / "validation.json")
    issues = read_jsonl(quality_dir / "issues.jsonl")
    review_pool = read_jsonl(quality_dir / "review_pool.jsonl")
    backflow = read_json(quality_dir / "review_backflow.json")

    trend = build_trend(history)
    alerts = build_alerts(gate, trend, validation)
    repair = build_repair_tracking(issues, review_pool, backflow)

    (ops_dir / "quality_trend.json").write_text(json.dumps(trend, ensure_ascii=False, indent=2), encoding="utf-8")
    (ops_dir / "quality_alerts.json").write_text(json.dumps(alerts, ensure_ascii=False, indent=2), encoding="utf-8")
    (ops_dir / "quality_repair_tracking.json").write_text(json.dumps(repair, ensure_ascii=False, indent=2), encoding="utf-8")
    write_markdown_reports(ops_dir, trend, alerts, repair)
    print(
        json.dumps(
            {
                "trend_path": "artifacts/ops/quality_trend.json",
                "alerts_path": "artifacts/ops/quality_alerts.json",
                "repair_path": "artifacts/ops/quality_repair_tracking.json",
                "stable_release_cycles": trend.get("stable_release_cycles", 0),
                "alert_count": alerts.get("alert_count", 0),
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
