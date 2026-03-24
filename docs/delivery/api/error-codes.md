# API 错误码字典（v1.1）

## 通用错误对象

```json
{
  "code": 400,
  "message": "invalid limit",
  "data": null,
  "trace_id": "..."
}
```

## 字段说明

- `code`：错误码（当前与 HTTP 状态码一致）
- `message`：错误消息
- `data`：错误时固定为 `null`
- `trace_id`：链路追踪 ID（同时在响应头 `X-Trace-Id` 返回）

## 错误码清单

| HTTP | code | 含义 | 典型触发场景 | 前端处理建议 |
|---|---:|---|---|---|
| 400 | 400 | 参数错误 | 缺少 `q`、`limit` 越界、`audience` 非法 | 保持当前页，提示用户修正参数 |
| 401 | 401 | 鉴权失败 | 未携带 `X-API-Key`、Key 无效/过期/禁用 | 提示重新配置密钥，阻断后续请求 |
| 404 | 404 | 资源不存在 | 访问不存在的 `topic_id` / `problem_id` / 路径 | 展示空态并提供返回入口 |
| 500 | 500 | 服务异常 | 运行时未捕获异常 | 统一错误提示并记录 `trace_id` |

## 常见 message 映射

| message | 语义 | 对应动作 |
|---|---|---|
| `missing or invalid api key` | 密钥缺失或无效 | 引导用户检查配置 |
| `missing q` | 检索词缺失 | 提示输入关键词 |
| `invalid audience` | audience 参数不合法 | 回退到默认 `teacher` 或提示修正 |
| `invalid limit` | limit 不是整数 | 重置为默认值 |
| `limit out of range [1,500]` | limit 超范围 | 限制输入范围后重试 |
| `not found` | 资源不存在 | 展示空态 |
