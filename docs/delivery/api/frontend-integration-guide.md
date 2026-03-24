# 前端接入手册（API v1.1）

## 1. 接入目标

- 本手册用于前端团队独立完成联调与开发。
- 约定以 `docs/delivery/api/openapi.yaml` 为接口契约基线。

## 2. 基础信息

- Base URL（本地）：`http://127.0.0.1:18080`
- 鉴权方式：请求头 `X-API-Key: <your_key>`
- 返回格式：统一 JSON 包装，包含 `code`、`message`、`data`、`trace_id`
- 追踪头：响应头 `X-Trace-Id` 与响应体 `trace_id` 一致

## 3. 联调顺序（推荐）

1. `GET /health`：确认服务可达
2. `GET /topics`、`GET /problems`：跑通列表页
3. `GET /topics/{topic_id}`、`GET /problems/{problem_id}`：跑通详情页
4. `GET /search` / `POST /search`：跑通检索页
5. `GET /quality/summary`：跑通质量看板入口数据

## 4. 核心参数约定

- `audience`：`teacher | student`，默认 `teacher`
- 分页参数：`offset`、`limit`
- 排序参数：`order_by`、`order`（`asc | desc`）
- 搜索参数：`q` 为检索必填字段（`/search`）

## 5. 错误处理约定

- `400`：参数错误，前端提示用户修正筛选条件
- `401`：鉴权失败，前端提示重新配置密钥或登录状态
- `404`：资源不存在，前端进入空态或返回上一级
- 5xx：服务异常，前端显示“稍后重试”并记录 `trace_id`

## 6. 浏览器跨域联调

- 跨域依赖服务端 CORS 配置。
- 前端联调时保持请求头最小集：
  - `Content-Type: application/json`
  - `X-API-Key: <your_key>`
  - 可选：`X-Trace-Id: <client_trace_id>`

## 7. 前端实现建议

- 列表页缓存分页结果，减少重复请求。
- 将 `trace_id` 写入错误日志与埋点，便于排障。
- 对 `grade_band` 为空场景回退显示“未标注”。
- 对数组字段（如 `method_tags`、`common_mistakes`）做空数组兜底。

## 8. 变更策略

- 兼容变更：优先新增字段，不删除既有字段。
- 破坏性变更：通过新版本路径发布，不直接替换 v1。
- 变更公告：以 `docs/delivery/api/api-changelog.md` 为准。

## 9. 配套文档

- 错误码字典：`docs/delivery/api/error-codes.md`
- 兼容映射表：`docs/delivery/api/compatibility-mapping.md`
- 联调问题记录：`docs/delivery/api/integration-issues-log.md`
