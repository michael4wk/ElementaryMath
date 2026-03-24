# 质量治理运营SOP

## 1. 目标

- 保持质量门禁稳定放行，避免关键指标回退。
- 建立“发现问题-人工复核-回流修复-复盘改进”的闭环机制。

## 2. 日常巡检（每日）

- 执行质量流水线并生成门禁报告。
- 检查 `artifacts/quality/gate_report.json` 是否存在阻断项。
- 检查 `artifacts/ops/quality_alerts.md` 告警明细并分派责任人。
- 对 `review_pool.jsonl` 中 P0/P1 与低置信样本安排人工复核。

## 3. 周度运营（每周）

- 审阅 `artifacts/ops/quality_trend.md` 与 `quality_trend.json`。
- 跟踪一致率、解析缺失率、易错点缺失率周环比变化。
- 跟踪 `quality_repair_tracking.json` 的复核关闭率与待处理数。
- 汇总高频冲突类型与热点专题，输出专项修复计划。

## 4. 月度复盘（每月）

- 基于 `artifacts/ops/monthly_quality_review.md` 完成复盘记录。
- 复盘项包含：关键问题、根因分析、修复动作、下月计划。
- 确认是否满足连续可放行周期目标与回滚演练要求。

## 5. 人工复核与回流

- 复核输入：`artifacts/quality/review_pool.jsonl`
- 复核反馈：`artifacts/quality/review_feedback.jsonl`
- 回流执行：`python3 tools/apply_review_feedback.py --project-root .`
- 回流产物：`artifacts/quality/review_backflow.json`

## 6. 发布与回滚判定

- 发布前必须检查：
  - `gate_report.can_release == true`
  - `quality_alerts` 无 critical 级告警
  - `release_diff.rollback_recommended == false`
- 不满足条件时禁止发布，并按回滚建议执行。

## 7. 标准执行命令

```bash
python3 tools/build_curated.py --project-root .
python3 tools/build_projection.py --project-root .
python3 tools/build_quality_report.py --project-root .
python3 tools/build_validation_report.py --project-root .
python3 tools/evaluate_quality_gate.py --project-root . --profile staging
python3 tools/build_quality_ops_report.py --project-root .
python3 tools/apply_review_feedback.py --project-root .
python3 tools/build_quality_release_diff.py --project-root . --profile staging
python3 tools/build_quality_observability.py --project-root .
python3 tools/build_acceptance_report.py --project-root .
```
