# 小学数学结构化底座实施说明

## 当前实现范围

- 阶段 A 基线盘点与规范落地
- 主从数据源策略落地（教师版主源，学生版投影）
- 增量接入所需的哈希与变更识别基础数据

## 目录说明

- `config/baseline_config.json`：基线处理配置
- `config/projection_rules.json`：教师/学生端字段投影规则
- `config/prerequisite_overrides.json`：前置关系人工映射覆盖配置
- `config/security_config.json`：API访问控制配置（API Key 与白名单）
- `tools/build_baseline.py`：生成文档资产清单与对齐报告
- `tools/normalize_documents.py`：将源文档转换到清洗层文本
- `tools/retry_failed_extractions.py`：重试抽取失败队列并更新状态
- `tools/build_curated.py`：从清洗层抽取 Topic/Explanation/Problem
- `tools/build_projection.py`：生成教师/学生端投影视图数据
- `tools/build_graph.py`：构建 topic 前置与后续关系图谱
- `tools/build_quality_report.py`：输出结构化内容质量报表
- `tools/build_validation_report.py`：输出完整性与一致性校验报告
- `tools/build_acceptance_report.py`：输出阶段验收报告
- `tools/ops_health_check.py`：执行接口巡检并输出告警报告
- `tools/build_rotation_report.py`：输出密钥轮换状态报告
- `tools/apply_rotation_phase.py`：按闸门结果执行轮换阶段推进
- `tools/backup_artifacts.py`：执行数据备份与恢复
- `tools/detect_asset_changes.py`：识别新增/修改/删除文档
- `api/minimal_api.py`：最小查询 API 服务
- `artifacts/baseline/`：脚本执行产物目录

## 运行方式

```bash
python3 tools/build_baseline.py --project-root .
python3 tools/normalize_documents.py --project-root .
python3 tools/retry_failed_extractions.py --project-root .
python3 tools/build_curated.py --project-root .
python3 tools/build_projection.py --project-root .
python3 tools/build_graph.py --project-root .
python3 tools/build_quality_report.py --project-root .
python3 tools/build_validation_report.py --project-root .
python3 tools/build_acceptance_report.py --project-root .
python3 tools/build_rotation_report.py --project-root .
python3 tools/ops_health_check.py --project-root . --base-url http://127.0.0.1:18080 --api-key dev-key-001 --readonly-api-key readonly-key-001 --disabled-api-key disabled-key-001 --revoked-api-key revoked-key-001 --rotate-old-api-key rotate-old-001 --rotate-new-api-key rotate-new-001
python3 tools/apply_rotation_phase.py --project-root . --base-url http://127.0.0.1:18080 --api-key dev-key-001
# 执行推进（默认在进入retire时自动禁用旧Key）
python3 tools/apply_rotation_phase.py --project-root . --base-url http://127.0.0.1:18080 --api-key dev-key-001 --apply --ticket OPS-001 --operator release-bot --change-reason retire-cutover-ready
# 回滚到cutover并自动恢复旧Key启用
python3 tools/apply_rotation_phase.py --project-root . --base-url http://127.0.0.1:18080 --api-key dev-key-001 --group core-search-key --target-phase cutover --rollback-enable-old --apply --force --ticket OPS-002 --operator release-bot --change-reason rollback-drill
python3 tools/backup_artifacts.py --project-root . --mode backup
python3 tools/detect_asset_changes.py --project-root . --commit-snapshot
python3 api/minimal_api.py --project-root . --host 127.0.0.1 --port 18080
```

## 输出文件

- `assets.jsonl`：逐文件资产清单（含哈希）
- `topics.jsonl`：按课程编号聚合后的主题清单
- `issues.jsonl`：命名与配对问题清单
- `summary.json`：统计摘要
- `artifacts/curated/topics.jsonl`：Topic 结构化对象
- `artifacts/curated/concepts.jsonl`：Concept 结构化对象
- `artifacts/curated/problems.jsonl`：Problem 结构化对象
- `artifacts/curated/explanations.jsonl`：Explanation 结构化对象
- `artifacts/serving/problems_student.jsonl`：学生端投影题目数据
- `artifacts/graph/topic_graph.jsonl`：Topic 图谱关系数据
- `artifacts/graph/chapter_graph.jsonl`：章节级聚合图谱数据
- `artifacts/graph/validation.json`：图谱前置关系校验报告
- `artifacts/quality/report.json`：结构化质量分析结果
- `artifacts/quality/validation.json`：完整性与一致性校验结果
- `artifacts/acceptance/report.md`：当前阶段验收报告
- `artifacts/ops/health_report.json`：接口巡检报告
- `artifacts/ops/health_history.jsonl`：巡检历史记录
- `artifacts/ops/rotation_report.json`：密钥轮换状态报告
- `artifacts/ops/rotation_actions.jsonl`：轮换推进/回滚操作审计日志
- `artifacts/ops/access.log`：API访问日志（含trace_id）
- `artifacts/changes/asset_changes.jsonl`：增量变更明细
- `artifacts/normalized/quarantine/failed_assets.jsonl`：抽取失败隔离清单
- `artifacts/normalized/quarantine/retry_queue.jsonl`：失败重试队列
- `artifacts/normalized/quarantine/retry_summary.json`：重试执行摘要

## API 端点

- `GET /health`：服务健康检查
- `GET /reload`：重新加载数据文件
- `GET /catalog/chapters`：章节目录（支持 `q/offset/limit`）
- `GET /topics`：主题列表（支持 `audience/q/chapter_id/domain/grade_band/difficulty/has_prerequisites/has_learning_objectives/order_by/order/offset/limit`）
- `GET /topics/{topic_id}`：主题详情（含图谱关系与题目统计）
- `GET /problems`：题目列表（支持 `audience/topic_id/chapter_id/grade_band/difficulty/method_tag/q/order_by/order/offset/limit`）
- `GET /facets/problems`：题目分面统计（支持 `audience/topic_id/chapter_id/q`）
- `GET /search`：统一检索（支持 `chapter_id/grade_band/difficulty/method_tag` 过滤）
- `POST /search`：统一检索（JSON body，参数同 GET 版）
  - 返回结果包含 `evidence` 字段（命中片段 `snippet`、命中位置 `match_index`、来源定位 `source_locator.line_hint`）
- `GET /graph/{topic_id}`：Topic 级依赖关系
- `GET /graph/chapter/{chapter_id}`：章节级依赖关系
- `GET /graph/validation`：图谱校验结果
- `GET /quality/summary`：质量报表摘要
- `GET /auth/whoami`：返回当前 API Key 的鉴权上下文
- `GET /auth/config`：返回当前鉴权配置摘要
- `GET /auth/reload`：热加载鉴权配置
- `GET /auth/rotation`：返回密钥轮换组与阶段
- `GET /auth/rotation/check`：返回密钥轮换配置校验结果
- `GET /auth/rotation/advice`：返回轮换阶段推进建议
- `GET /auth/rotation/gate`：返回轮换推进安全闸门结果
- `GET /auth/rotation/plan`：返回轮换阶段执行计划预览

## 响应规范

- 所有接口响应均包含 `trace_id`，并通过响应头 `X-Trace-Id` 返回
- 服务端访问日志记录在 `artifacts/ops/access.log`
- 访问日志新增 `authorized/auth_reason/api_key_id/api_key_name/audience_hint/revoked_reason` 字段

## 访问控制

- 启用方式：编辑 `config/security_config.json` 中 `auth_enabled`
- 鉴权方式：除白名单路径外，接口需携带请求头 `X-API-Key`
- 默认白名单：`/health`
- `api_keys` 支持两种格式：字符串（默认全路径权限）或对象规则（`name/key/enabled/not_before/not_after/allow_all/allow_prefixes/allow_audiences`）
- 示例：`readonly-key-001` 可限制只访问 `/topics`、`/problems`、`/catalog`、`/auth` 等前缀，且仅允许 `teacher` 受众
- 可通过 `enabled/not_before/not_after` 实现禁用、启用时间窗与过期控制
- `revoked_keys` 支持字符串或对象（`key/reason`），用于吊销已签发 Key
- `rotation_groups` 支持 `name/old_key/new_key/phase`，当 `phase=cutover` 时旧 Key 会被拒绝
- `rotation_gate` 支持安全闸门配置（如 `min_consecutive_ok`）
- `apply_rotation_phase.py` 默认仅预览，`--apply` 执行；`--retire-old-action` 支持 `disable/revoke/keep`
- `apply_rotation_phase.py` 支持 `--target-phase` 定向切换，`--rollback-enable-old` 在回滚时自动恢复旧Key
- `apply_rotation_phase.py` 在 `--apply` 模式下要求提供 `--ticket` 与 `--operator`，并可记录 `--change-reason`

## 抽取质量优化

- 解析步骤支持回退抽取（原式/解/步骤/思路/等号行）
- 年级识别支持阿拉伯数字与中文数字（如 `4年级`、`四年级`）
- 难度识别支持数字星级与星符号计数（如 `2星`、`★★★`）
- 缺失年级与难度支持按专题众数回填（保留 `grade_source/difficulty_source`）
- 缺失方法标签支持按专题标题回填（保留 `method_tag_source`）
