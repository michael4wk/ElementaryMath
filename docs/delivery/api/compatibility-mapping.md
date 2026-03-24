# 接口兼容映射表（v1.1）

## 映射原则

- 对外契约以 `docs/delivery/api/openapi.yaml` 为准。
- 现网路径保持兼容，不做破坏性替换。
- 新增能力优先通过新增路径或新增字段实现。

## 核心接口映射

| 能力域 | 契约路径 | 实现路径 | 方法 | 兼容状态 |
|---|---|---|---|---|
| 健康检查 | `/health` | `/health` | GET | 完全一致 |
| 章节目录 | `/catalog/chapters` | `/catalog/chapters` | GET | 完全一致 |
| 主题列表 | `/topics` | `/topics` | GET | 完全一致 |
| 主题详情 | `/topics/{topic_id}` | `/topics/{topic_id}` | GET | 完全一致 |
| 题目列表 | `/problems` | `/problems` | GET | 完全一致 |
| 题目详情 | `/problems/{problem_id}` | `/problems/{problem_id}` | GET | 完全一致 |
| 统一检索 | `/search` | `/search` | GET/POST | 完全一致 |
| 质量摘要 | `/quality/summary` | `/quality/summary` | GET | 完全一致 |
| 质量校验 | `/quality/validation` | `/quality/validation` | GET | 完全一致 |
| 门禁报告 | `/quality/gate/report` | `/quality/gate/report` | GET | 完全一致 |
| 门禁评估 | `/quality/gate/evaluate` | `/quality/gate/evaluate` | GET/POST | 完全一致 |

## 暂未纳入最小交付集但保持可用

- `/graph/{topic_id}`
- `/graph/chapter/{chapter_id}`
- `/graph/validation`
- `/facets/problems`
- `/auth/*`

## 后续版本预留

- 如需路径版本化，采用 `/v2/...` 增量发布，不迁移现有 v1 路径。
