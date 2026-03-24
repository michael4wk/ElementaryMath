# API 请求响应示例（v1.1）

## 1. 健康检查

### 请求

```bash
curl -s 'http://127.0.0.1:18080/health'
```

### 响应（示例）

```json
{"code":0,"message":"ok","data":{"status":"up"},"trace_id":"..."}
```

## 2. 主题列表

### 请求

```bash
curl -s 'http://127.0.0.1:18080/topics?audience=teacher&limit=5' \
  -H 'X-API-Key: your-key'
```

### 响应（示例结构）

```json
{"code":0,"message":"ok","data":[{"topic_id":"...","title":"..."}],"meta":{"total":0,"offset":0,"limit":5},"trace_id":"..."}
```

## 3. 题目详情

### 请求

```bash
curl -s 'http://127.0.0.1:18080/problems/problem_xxx?audience=teacher' \
  -H 'X-API-Key: your-key'
```

### 响应（示例结构）

```json
{"code":0,"message":"ok","data":{"problem_id":"problem_xxx","stem":"...","answer":"..."},"trace_id":"..."}
```

## 4. 统一检索（POST）

### 请求

```bash
curl -s 'http://127.0.0.1:18080/search' \
  -H 'Content-Type: application/json' \
  -H 'X-API-Key: your-key' \
  -d '{"audience":"teacher","q":"分数加法","limit":5}'
```

### 响应（示例结构）

```json
{"code":0,"message":"ok","data":{"topics":[],"problems":[]},"meta":{"topic_total":0,"problem_total":0,"limit":5},"trace_id":"..."}
```

## 5. 门禁评估（GET）

### 请求

```bash
curl -s 'http://127.0.0.1:18080/quality/gate/evaluate?gate_profile=staging' \
  -H 'X-API-Key: your-key'
```

### 响应（示例结构）

```json
{"code":0,"message":"ok","data":{"profile":"staging","can_release":true,"blockers":[],"warnings":[]},"trace_id":"..."}
```

## 6. 错误响应（401）

### 请求

```bash
curl -s 'http://127.0.0.1:18080/topics?audience=teacher'
```

### 响应（示例结构）

```json
{"code":401,"message":"missing or invalid api key","data":null,"trace_id":"..."}
```
