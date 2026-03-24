#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
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
    baseline = read_json(root / "artifacts" / "baseline" / "summary.json")
    normalized = read_json(root / "artifacts" / "normalized" / "summary.json")
    curated = read_json(root / "artifacts" / "curated" / "summary.json")
    graph = read_json(root / "artifacts" / "graph" / "summary.json")
    quality = read_json(root / "artifacts" / "quality" / "report.json")
    validation = read_json(root / "artifacts" / "quality" / "validation.json")
    gate = read_json(root / "artifacts" / "quality" / "gate_report.json")
    changes = read_json(root / "artifacts" / "changes" / "summary.json")
    ops_health = read_json(root / "artifacts" / "ops" / "health_report.json")
    security_conf = read_json(root / "config" / "security_config.json")
    access_log_path = root / "artifacts" / "ops" / "access.log"
    has_backup = (root / "backups").exists() and any((root / "backups").iterdir())

    total_attempted = int(normalized.get("total_attempted", 0) or 0)
    success_count = int(normalized.get("success_count", 0) or 0)
    extract_success_rate = round((success_count * 100.0 / total_attempted), 2) if total_attempted else 0.0
    problem_quality = quality.get("problem_quality", {})
    topic_quality = quality.get("topic_quality", {})
    explanation_quality = quality.get("explanation_quality", {})
    completeness = validation.get("completeness", {})
    consistency = validation.get("consistency", {})
    traceability = validation.get("traceability", {})

    report = {
        "snapshot": {
            "assets_total": baseline.get("total_assets", 0),
            "topics_total": curated.get("topic_count", 0),
            "problems_total": curated.get("problem_count", 0),
            "extract_success_rate_pct": extract_success_rate,
            "graph_edges": graph.get("edge_count", 0),
            "chapter_edges": graph.get("chapter_edge_count", 0),
        },
        "quality": {
            "missing_method_tags_rate_pct": problem_quality.get("missing_method_tags_rate_pct", 0),
            "missing_grade_band_rate_pct": problem_quality.get("missing_grade_band_rate_pct", 0),
            "missing_difficulty_rate_pct": problem_quality.get("missing_difficulty_rate_pct", 0),
            "empty_analysis_rate_pct": problem_quality.get("empty_analysis_rate_pct", 0),
            "missing_learning_objectives_rate_pct": topic_quality.get("missing_learning_objectives_rate_pct", 0),
            "missing_common_mistakes_rate_pct": topic_quality.get("missing_common_mistakes_rate_pct", 0),
            "missing_summary_rate_pct": explanation_quality.get("missing_summary_rate_pct", 0),
            "learning_objectives_coverage_pct": completeness.get("learning_objectives_coverage_pct", 0),
            "common_mistakes_coverage_pct": completeness.get("common_mistakes_coverage_pct", 0),
            "method_tags_coverage_pct": completeness.get("method_tags_coverage_pct", 0),
            "answer_analysis_consistency_rate_pct": consistency.get("answer_analysis_consistency_rate_pct", 0),
            "source_ref_coverage_pct": traceability.get("source_ref_coverage_pct", 0),
            "gate_can_release": gate.get("can_release", False),
            "gate_blocker_count": len(gate.get("blockers", [])) if isinstance(gate.get("blockers", []), list) else 0,
        },
        "graph_validation": {
            "topic_cycle_detected": graph.get("topic_cycle_detected", None),
            "chapter_cycle_detected": graph.get("chapter_cycle_detected", None),
            "override_error_count": graph.get("override_error_count", None),
        },
        "incremental": {
            "change_count": changes.get("change_count", None),
            "added": changes.get("added", None),
            "modified": changes.get("modified", None),
            "deleted": changes.get("deleted", None),
        },
        "acceptance_view": {
            "data_preparation_ready": bool(baseline.get("total_assets", 0) > 0 and baseline.get("paired_topics", 0) > 0),
            "extraction_ready": bool(extract_success_rate >= 95.0),
            "model_ready_minimum": bool(curated.get("topic_count", 0) > 0 and curated.get("problem_count", 0) > 0),
            "completeness_ready": bool(completeness.get("required_objects_ready", False) and completeness.get("fields_ready", False)),
            "consistency_ready": bool(consistency.get("logic_consistent_ready", False)),
            "traceability_ready": bool(traceability.get("traceability_ready", False)),
            "graph_ready": bool(graph.get("edge_count", 0) > 0 and graph.get("topic_cycle_detected", True) is False),
            "incremental_ready": bool(changes.get("change_count", 1) is not None),
            "quality_gate_ready": bool(gate.get("can_release", False)),
            "ops_ready": bool(
                bool(ops_health.get("ok", False))
                and access_log_path.exists()
                and bool(security_conf.get("auth_enabled", False))
                and has_backup
            ),
        },
    }

    out_dir = root / "artifacts" / "acceptance"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        "# 当前阶段验收报告",
        "",
        "## 核心快照",
        f"- 资产总量: {report['snapshot']['assets_total']}",
        f"- 主题总量: {report['snapshot']['topics_total']}",
        f"- 题目总量: {report['snapshot']['problems_total']}",
        f"- 抽取成功率: {report['snapshot']['extract_success_rate_pct']}%",
        f"- 图谱边数: {report['snapshot']['graph_edges']} (章节边数: {report['snapshot']['chapter_edges']})",
        "",
        "## 质量指标",
        f"- 方法标签缺失率: {report['quality']['missing_method_tags_rate_pct']}%",
        f"- 年级缺失率: {report['quality']['missing_grade_band_rate_pct']}%",
        f"- 难度缺失率: {report['quality']['missing_difficulty_rate_pct']}%",
        f"- 解析缺失率: {report['quality']['empty_analysis_rate_pct']}%",
        f"- 学习目标缺失率: {report['quality']['missing_learning_objectives_rate_pct']}%",
        f"- 易错点缺失率: {report['quality']['missing_common_mistakes_rate_pct']}%",
        f"- 学习目标覆盖率: {report['quality']['learning_objectives_coverage_pct']}%",
        f"- 易错点覆盖率: {report['quality']['common_mistakes_coverage_pct']}%",
        f"- 方法标签覆盖率: {report['quality']['method_tags_coverage_pct']}%",
        f"- 题干-答案-解析一致率: {report['quality']['answer_analysis_consistency_rate_pct']}%",
        f"- source_ref覆盖率: {report['quality']['source_ref_coverage_pct']}%",
        f"- 发布门禁可放行: {report['quality']['gate_can_release']}",
        f"- 门禁阻断项数量: {report['quality']['gate_blocker_count']}",
        "",
        "## 自动验收视图",
        f"- 数据准备就绪: {report['acceptance_view']['data_preparation_ready']}",
        f"- 提取清洗就绪: {report['acceptance_view']['extraction_ready']}",
        f"- 结构化最小就绪: {report['acceptance_view']['model_ready_minimum']}",
        f"- 完整性就绪: {report['acceptance_view']['completeness_ready']}",
        f"- 一致性就绪: {report['acceptance_view']['consistency_ready']}",
        f"- 可追溯就绪: {report['acceptance_view']['traceability_ready']}",
        f"- 图谱就绪: {report['acceptance_view']['graph_ready']}",
        f"- 增量接入就绪: {report['acceptance_view']['incremental_ready']}",
        f"- 质量门禁就绪: {report['acceptance_view']['quality_gate_ready']}",
        f"- 运维就绪: {report['acceptance_view']['ops_ready']}",
    ]
    (out_dir / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({"report_json": "artifacts/acceptance/report.json", "report_md": "artifacts/acceptance/report.md"}, ensure_ascii=False))


if __name__ == "__main__":
    main()
