# 契约治理与评审流程（v1.1）

## 1. 契约冻结窗口

- 每周二至周四为契约冻结窗口。
- 冻结窗口内仅允许兼容性变更（新增字段、补充示例、补充文档）。
- 破坏性变更（删字段、改语义、改路径）仅允许在窗口外发起，并通过版本升级发布。

## 2. 变更评审流程

1. 发起方提交变更说明与影响面。
2. 后端确认实现可行性与回滚策略。
3. 前端确认字段语义与兼容处理。
4. 通过一致性校验脚本与最小联调回归后合入。

## 3. 一致性校验

- 校验脚本：`tools/check_api_contract_consistency.py`
- 校验目标：
  - OpenAPI 路径在服务实现中可命中
  - 契约中包含 `X-Trace-Id` 与 `trace_id` 约定
- 执行命令：
  - `python3 tools/check_api_contract_consistency.py --project-root .`

## 4. 兼容策略

- 新增优先：优先新增字段，不删除既有字段。
- 弃用声明：需在 `api-changelog.md` 声明弃用窗口。
- 版本升级：破坏性变更通过新版本路径发布。

## 5. 交付审计

- 变更记录：`docs/delivery/api/api-changelog.md`
- 联调问题：`docs/delivery/api/integration-issues-log.md`
- 验收基线：`artifacts/acceptance/report.md`
