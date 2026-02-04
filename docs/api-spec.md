# Echoman API 接口文档

> **运行时口径（2026-02-04）**：后端已切换为纯 Chroma 向量库；整体归并候选 Top-K=3；新建 Topic 热度截断禁用（`global_merge_new_topic_keep_ratio=1.0`）。

## 概述

- Base URL：`/api/v1`
- Content-Type：`application/json; charset=utf-8`
- 自由模式：`/chat/ask` 的 `mode=global` 需要 `free_token`（由 `/free/verify` 发放）

## 枚举与通用约定

- `platform`: `weibo|zhihu|toutiao|sina|netease|baidu|hupu`
- `topic_status`: `active|ended`
- `topic_category`: `entertainment|current_affairs|sports_esports`
- `chat_mode`: `topic|global`

通用分页：`?page=1&size=50`（部分列表支持）

错误返回（HTTP 4xx/5xx，FastAPI 默认格式）：
```
{"detail": "错误信息"}
```

---

## 健康检查

- GET `/health`
- 200：
```
{"status":"ok","version":"0.1.0","env":"development"}
```

---

## 采集与调度

- POST `/ingest/run`
  - 描述：手动触发一次采集（定时任务为 8:00-22:00 每 2 小时一次）
  - 入参：
    ```json
    {"platforms":["weibo","zhihu"],"limit":30}
    ```
  - 出参：
    ```json
    {"run_id":"run_xxx","scheduled":true,"message":"采集任务已提交，运行ID: run_xxx"}
    ```

- GET `/ingest/runs`
  - 查询最近运行：`?limit=20`
  - 出参：
    ```json
    {
      "items":[
        {
          "run_id":"run_xxx",
          "start_at":"2026-02-04T08:00:01",
          "end_at":"2026-02-04T08:00:12",
          "status":"success",
          "total":210,
          "success":208,
          "failed":2,
          "parse_success_rate":0.99
        }
      ]
    }
    ```

- GET `/ingest/sources/status`
  - 描述：平台连接器健康状况
  - 出参：
    ```json
    {
      "items":[
        {
          "platform":"weibo",
          "last_success_at":"2026-02-04T08:00:12",
          "last_error":null,
          "success_rate_24h":1.0,
          "avg_latency_ms":820,
          "records_per_run":30,
          "auth_mode":"api",
          "notes":"使用 weibo API/爬虫"
        }
      ]
    }
    ```

---

## 话题（Topics）

- GET `/topics`
  - 过滤：`?status=active&category=entertainment&keyword=苹果&today_only=false&order=echo_rank&page=1&size=50`
  - `order` 支持：`echo_rank|last_active_desc|heat_desc|intensity_desc`
  - 出参（示例）：
    ```json
    {
      "page":1,
      "size":50,
      "total":256,
      "items":[
        {
          "topic_id":"123",
          "title":"苹果发布会",
          "summary":"苹果发布会",
          "intensity_raw":138,
          "intensity_norm":0.15,
          "length_hours":36.0,
          "length_days":1.5,
          "first_seen":"2026-02-04T10:05:00",
          "last_active":"2026-02-04T22:20:00",
          "platforms":["weibo","zhihu"],
          "platform_mentions":{"weibo":12,"zhihu":6},
          "status":"active"
        }
      ]
    }
    ```

- GET `/topics/today`
  - 描述：仅返回“今天创建”的话题列表
  - 参数：`?order=echo_rank&page=1&size=50`
  - 出参：与 `/topics` 相同结构

- GET `/topics/{topic_id}`
  - 出参（示例）：
    ```json
    {
      "id":123,
      "title_key":"苹果发布会",
      "first_seen":"2026-02-04T10:05:00",
      "last_active":"2026-02-04T22:20:00",
      "status":"active",
      "category":"entertainment",
      "intensity_total":138,
      "interaction_total":521034,
      "current_heat_normalized":0.15,
      "heat_percentage":15.0,
      "length_display":"1天12小时",
      "summary":null
    }
    ```

- GET `/topics/{topic_id}/timeline`
  - 参数：`?platform=weibo&page=1&size=50`
  - 出参（示例）：
    ```json
    {
      "topic_summary": null,
      "items": [
        {
          "node_id":1,
          "topic_id":123,
          "timestamp":"2026-02-04T09:10:00",
          "title":"...",
          "content":"...",
          "source_platform":"weibo",
          "source_url":"https://...",
          "captured_at":"2026-02-04T09:12:00",
          "engagement":120,
          "duplicate_count":3,
          "time_range_start":"2026-02-04T08:50:00",
          "time_range_end":"2026-02-04T09:10:00",
          "all_platforms":["weibo","zhihu"],
          "all_source_urls":["https://...","https://..."],
          "all_timestamps":["2026-02-04T09:10:00","2026-02-04T08:50:00"]
        }
      ]
    }
    ```

---

## 分类（Categories）

- GET `/categories`
  - 出参：
    ```json
    {
      "items":[
        {"key":"entertainment","display":"娱乐八卦类事件"},
        {"key":"current_affairs","display":"社会实事类事件"},
        {"key":"sports_esports","display":"体育电竞类事件"}
      ]
    }
    ```

- GET `/categories/metrics/summary`
  - 参数：`?window_days=365&ended_only=false&use_cache=true`
  - 出参（示例）：
    ```json
    {
      "window_days":365,
      "ended_only":false,
      "computed_at":"2026-02-04",
      "source":"precomputed",
      "items":[
        {
          "category":"entertainment",
          "avg_length_hours":76.0,
          "max_length_hours":160.0,
          "min_length_hours":36.0,
          "avg_length_display":"3天4小时",
          "max_length_display":"6天16小时",
          "min_length_display":"1天12小时",
          "max_length_topic_id":123,
          "min_length_topic_id":456,
          "topics_count":428,
          "topics_active":120,
          "topics_ended":308,
          "intensity_sum":120345,
          "intensity_avg":281.2
        }
      ]
    }
    ```

- GET `/categories/metrics/timeseries`
  - 参数：`?category=entertainment&metric=avg_length_hours&days=30`
  - 出参：
    ```json
    {
      "category":"entertainment",
      "metric":"avg_length_hours",
      "data":[{"date":"2026-02-01","value":62.0}]
    }
    ```

- POST `/categories/metrics/recompute`
  - 参数（Query）：`?since_date=2026-02-01&rebuild=true`
  - 出参：
    ```json
    {"status":"success","target_date":"2026-02-04","saved_count":3,"computed_at":"2026-02-04T01:00:00"}
    ```

---

## 管理（Admin）

- GET `/admin/metrics/summary`
  - 出参（示例）：
    ```json
    {
      "ingest":{
        "last_run":{"run_id":"run_xxx","status":"success","start_at":"...","end_at":"...","duration_ms":81234},
        "per_platform":[],
        "halfday_merge":{"last_merge_at":null,"period":"PM","input_items":0,"kept_items":0,"dropped_items":0,"keep_rate":0.0,"drop_rate":0.0,"merge_groups":0,"avg_occurrence":0.0},
        "global_merge":{"last_merge_at":null,"input_events":0,"merge_count":0,"new_count":0,"merge_rate":0.0},
        "merge_reject_rate":0.0,
        "topics_total":2189,
        "topics_active":428,
        "topics_ended":1761,
        "topics_new_per_day":0.0
      },
      "chat":{"citation_hit_rate":0.0,"latency_p95_ms":0,"timeout_rate":0.0,"failure_rate":0.0},
      "cost":{"by_task":[],"by_provider":[]}
    }
    ```

- GET `/admin/metrics/timeseries`
  - 参数：`?metric=topics_new_per_day&days=30`
  - metric 支持：`topics_new_per_day|topics_total_per_day|topics_active_per_day|topics_ended_per_day`
  - 出参：
    ```json
    {"metric":"topics_new_per_day","data":[{"date":"2026-02-01","value":12}]}
    ```

- GET `/admin/categories`
  - 出参：
    ```json
    {
      "items":[
        {"key":"entertainment","display":"娱乐八卦类"},
        {"key":"current_affairs","display":"社会实事类"},
        {"key":"sports_esports","display":"体育电竞类"}
      ]
    }
    ```

---

## 对话（Chat / RAG）

- POST `/chat/ask`
  - 入参：
    ```json
    {
      "mode":"topic",
      "topic_id":123,
      "query":"和去年的相比有哪些变化？",
      "stream":false,
      "free_token":"free_xxx",
      "history":[{"role":"user","content":"..."}]
    }
    ```
  - 出参（示例）：
    ```json
    {
      "answer":"...",
      "citations":[{"topic_id":123,"node_id":1,"source_url":"https://...","snippet":"...","platform":"weibo"}],
      "diagnostics":{
        "latency_ms":1520,
        "tokens_prompt":1200,
        "tokens_completion":180,
        "context_chunks":5,
        "original_chunks":8,
        "token_optimization":{"used_context_tokens":1200,"available_context_tokens":20000}
      }
    }
    ```

- POST `/chat/ask`（SSE 流式）
  - 入参：同上，但设置 `"stream": true`
  - 出参：SSE 事件流（`event: token|citations|done|error`）
    ```
    event: token
    data: {"content":"这是"}

    event: citations
    data: {"citations":[{"topic_id":123,"node_id":1,"source_url":"...","snippet":"...","platform":"weibo"}]}

    event: done
    data: {"diagnostics":{"latency_ms":1520,"tokens_prompt":1200,"tokens_completion":180,"context_chunks":5,"original_chunks":8}}
    ```

- POST `/chat/create`
  - 入参：`{"mode":"global","topic_id":null}`
  - 出参：`{"id":1,"mode":"global","topic_id":null,"created_at":"..."}`

- GET `/chat/health`
  - 出参：`{"status":"ok","service":"chat"}`

---

## 自由模式（Free Mode）

- POST `/free/verify`
  - 入参：`{"code":"AB12CD34"}`
  - 出参：
    ```json
    {"valid":true,"token":"free_xxx","expires_at":"2026-02-08T12:00:00"}
    ```
