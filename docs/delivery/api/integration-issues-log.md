# 前端联调问题记录（v1.1）

## 使用说明

- 每条问题记录一行，持续追加。
- 状态流转：`open -> in_progress -> resolved -> verified`
- 问题关闭前需补充回归结果与 `trace_id`（如有）。

| issue_id | 日期 | 场景 | 描述 | 影响接口 | 状态 | owner | 回归结论 |
|---|---|---|---|---|---|---|---|
| FE-INT-001 | 2026-03-24 | 浏览器预检 | OPTIONS 预检与 CORS 头验证 | `/topics` | verified | backend | 已通过本地回归 |
| FE-INT-002 | 2026-03-24 | 题目详情 | 补齐 `GET /problems/{problem_id}` | `/problems/{problem_id}` | verified | backend | 已通过本地回归 |
