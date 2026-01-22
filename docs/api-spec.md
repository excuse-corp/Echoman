# Echoman API 接口文档

> **实现状态说明**：
> - ✅ **已实现** - 后端代码已完成
> - 🚧 **部分实现** - 核心功能已实现，部分特性待完善
> - ❌ **未实现** - 仅为规划，代码未实现
>
> **运行时口径（2026-01-22）**：后端已切换为纯 Chroma 向量库；整体归并候选 Top-K=3、时间窗 180 天；新建 Topic 热度截断当前已禁用（`GLOBAL_MERGE_NEW_TOPIC_KEEP_RATIO`=1.0，保留全部）。API 字段未变更，语义保持兼容。

## 概述

- Base URL：`/api/v1`
- Auth：`Authorization: Bearer <token>`（可替换为内网白名单/签名鉴权）
- Content-Type：`application/json; charset=utf-8`
- 幂等：对写操作支持 `Idempotency-Key` 头；返回 `X-Request-ID` 便于追踪。
- 实现说明：对话与判定/摘要/分类的 AI 编排建议采用 LangChain + LangGraph；SSE 流式基于 LangChain astream 事件。

## 枚举与通用对象

- `platform`: `weibo|zhihu|toutiao|sina|netease|baidu|hupu`
  - 注：原计划的 `tencent|xhs|douyin` 已因技术难度移除
- `topic_status`: `active|ended`
- `topic_category`: `entertainment|current_affairs|sports_esports`
- `chat_mode`: `topic|global`

通用分页：
- `?page=1&size=20`，响应含 `page, size, total`。

错误响应：
```
{
  "error": {
    "code": "INVALID_ARGUMENT",
    "message": "...",
    "request_id": "..."
  }
}
```

## 健康检查

- ✅ GET `/health`
- 200：`{"status":"ok","version":"0.1.0","env":"development"}`

## 调度与采集

- ✅ POST `/ingest/run`
  - 描述：手动触发一次采集（常规由定时器在 8:00-22:00 每 2 小时执行，共 8 次：8:00, 10:00, 12:00, 14:00, 16:00, 18:00, 20:00, 22:00）。
  - 说明：每日4次归并，每次2阶段：
    - **清晨（MORN）**：08:05阶段一，08:20阶段二（处理08:00采集数据）
    - **上午（AM）**：12:05阶段一，12:20阶段二（处理10:00/12:00采集数据）
    - **下午（PM）**：18:05阶段一，18:20阶段二（处理14:00/16:00/18:00采集数据）
    - **傍晚（EVE）**：22:05阶段一，22:20阶段二（处理20:00/22:00采集数据）
  - 采集侧噪音过滤：误操作条目（如“点击查看更多实时热点”或热榜列表页链接）会在入库前被拦截。
  - 入参：`{ "platforms": ["weibo", "zhihu"], "limit": 30 }`（可选）
  - 出参：`{ "run_id": "...", "scheduled": true, "message": "..." }`

- ✅ GET `/ingest/runs`
  - 查询最近运行：`?limit=20`
  - 出参：列表包含 `run_id, start_at, end_at, status, total, success, failed, parse_success_rate`。

- ✅ GET `/ingest/sources/status`
  - 描述：返回各平台连接器健康状况，可用于阶段 1 验收。
  - 出参：
```
{
  "items": [
    {
      "platform": "weibo",
      "last_success_at": "2025-05-10T02:01:24Z",
      "last_error": null,
      "success_rate_24h": 0.97,
      "avg_latency_ms": 820,
      "records_per_run": 30,
      "auth_mode": "cookie",
      "notes": "使用 hotSearch 接口"
    },
    {"platform": "zhihu", ...}
  ]
}
```

## 话题（Topics）

- ✅ GET `/topics`
  - 过滤：`?status=active&category=entertainment&keyword=苹果&page=1&size=20&order=last_active_desc|heat_desc|intensity_desc`
  - 说明：支持按最后活跃时间、热度峰值、强度排序
  - 注意：不支持 `platform` 参数筛选（该筛选在时间线API中支持）
  - 出参（示例）：
```
{
  "page":1,
  "size":20,
  "total":256,
  "items":[{
    "id":"t_123",
    "title_key":"苹果发布会",
    "first_seen":"2025-05-01T10:05:00Z",
    "last_active":"2025-05-02T22:20:00Z",
    "status":"active",
    "category":"entertainment",
    "intensity_total": 138,
    "interaction_total": 521034
  }]
}
```

- ✅ GET `/topics/{topic_id}`
  - 出参：基础信息 + 当前摘要快照（摘要功能待实现）：
```
{
  "id":"t_123",
  "title_key":"苹果发布会",
  "status":"active",
  "category":"entertainment",
  "first_seen":"...",
  "last_active":"...",
  "length_display":"1天12小时",
  "intensity_total":138,
  "interaction_total":521034,
  "current_heat_normalized": 0.15,
  "heat_percentage": 15.0,
  "summary": {
    "id":"s_789",
    "content":"...（主题摘要，含要点与证据参考）...",
    "updated_at":"..."
  }
}
```
  - 字段说明：`current_heat_normalized` / `heat_percentage` 为**跨归并周期的热度峰值**。

- ✅ GET `/topics/{topic_id}/timeline`
  - 过滤：`?platform=weibo&page=1&size=50`
  - 出参：
```
{
  "items":[{
    "node_id":"n_001",
    "source_item_id":"si_001",
    "platform":"weibo",
    "title":"...",
    "summary":"...",
    "url":"https://...",
    "published_at":"...",
    "interactions": {"repost":10, "comment":5, "like":100}
  }]
}
```



## 对话（RAG）

- ✅ POST `/chat/ask`
  - 状态：**已实现** - 非流式版本
  - 入参：
```
{
  "chat_mode": "topic",       // topic|global
  "topic_id": "t_123",        // topic 模式必填
  "query": "和去年的相比，有哪些改进？",
  "top_k": 5,                  // global 模式可选
  "stream": false              // 可选
}
```
  - 出参（非流式）：
```
{
  "message_id":"m_456",
  "answer":"...（含明确引用的回答）...",
  "citations":[{
    "topic_id":"t_123",
    "node_id":"n_001",
    "source_url":"https://...",
    "snippet":"..."
  }],
  "diagnostics":{
    "latency_ms": 1520,
    "tokens_prompt": 1200,
    "tokens_completion": 180,
    "provider":"openai",
    "model":"gpt-4o-mini"
  },
  "fallback":"无法确认" // 当检索证据不足时返回的消息（可为空）
}
```

- ✅ POST `/chat/ask` (流式版本)
  - 状态：**已实现** - SSE流式输出已完成
  - 入参：同上，但设置 `"stream": true`
  - 出参：SSE事件流
  ```
  event: token
  data: {"content":"这是"}
  
  event: token
  data: {"content":"流式"}
  
  event: token
  data: {"content":"输出"}
  
  event: citations
  data: {"citations":[{"topic_id":"t_123","node_id":"n_001","source_url":"...","snippet":"...","platform":"weibo"}]}
  
  event: done
  data: {"diagnostics":{"latency_ms":1520,"tokens_prompt":1200,"tokens_completion":180,"context_chunks":5}}
  
  event: error
  data: {"message":"错误描述"}
  ```
  - 测试状态：✅ 通过
  - 集成文档：[SSE集成指南](./sse-integration-guide.md)

- ✅ POST `/chat/create`
  - 状态：**已实现** - 用于创建新会话
  - 入参：`{"mode":"global","topic_id":null}`
  - 出参：`{"id":1,"mode":"global","topic_id":null,"created_at":"..."}`

## 管理与统计（后台页面数据源）

- 🚧 GET `/admin/metrics/summary`
  - 状态：**部分实现** - 基础统计已实现，归并指标待完善
  - 出参：
```
{
  "ingest":{
    "last_run": {"run_id":"...","status":"success","start_at":"...","end_at":"...","duration_ms": 81234},
    "per_platform": [{"platform":"weibo","success":30,"failed":2,"parse_success_rate":0.94}],
    "event_merge": {
      "last_merge_at": "2025-11-07T22:05:00+08:00",
      "period": "EVE",
      "input_items": 459,
      "kept_items": 377,
      "dropped_items": 82,
      "keep_rate": 0.821,
      "drop_rate": 0.179,
      "merge_groups": 132,
      "avg_occurrence": 2.86
    },
    "global_merge": {
      "last_merge_at": "2025-11-07T22:20:00+08:00",
      "period": "EVE",
      "input_events": 132,
      "merge_count": 56,
      "new_count": 76,
      "merge_rate": 0.424
    },
    "merge_reject_rate": 0.27,
    "topics_total": 2189,
    "topics_active": 428,
    "topics_ended": 1761,
    "topics_new_per_day": 52
  },
  "chat":{
    "citation_hit_rate": 0.88,
    "latency_p95_ms": 2310,
    "timeout_rate": 0.02,
    "failure_rate": 0.01
  },
  "cost":{
    "by_task":[{"task":"merge","prompt":15230,"completion":1820},{"task":"summarize","prompt":...}],
    "by_provider":[{"provider":"openai","usd":12.38}]
  }
}
```

### 分类相关（新增）

- ✅ GET `/categories`
  - 出参：
```
{
  "items": [
    {"key":"entertainment","display":"娱乐八卦类"},
    {"key":"current_affairs","display":"社会时事类"},
    {"key":"sports_esports","display":"体育电竞类"}
  ]
}
```

- ✅ GET `/categories/metrics/summary`
  - 说明：三类的回声平均/最长/最短时长与辅助指标。
  - 参数：`?window_days=365&ended_only=false&use_cache=true`
  - 注意：默认窗口为365天（一年），支持缓存加速
  - 出参：
```
{
  "window_days":30,
  "ended_only":false,
  "items":[
    {
      "category":"entertainment",
      "avg_length_hours": 76.0,
      "max_length_hours": 160.0,
      "min_length_hours": 36.0,
      "avg_length_display":"3天4小时",
      "max_length_display":"6天16小时",
      "min_length_display":"1天12小时",
      "max_length_topic_id":"t_abc",
      "min_length_topic_id":"t_xyz",
      "topics_count": 428,
      "intensity_sum": 120345
    },
    {"category":"current_affairs", ...},
    {"category":"sports_esports", ...}
  ]
}
```

- ✅ GET `/categories/metrics/timeseries`
  - 参数：`?category=entertainment&metric=avg_length_hours&days=30`
  - 出参：`[{"date":"2025-05-01","value":62.0}, ...]`
  - 支持的指标：`avg_length_hours`, `max_length_hours`, `min_length_hours`, `topics_count`, `intensity_sum` 等

- ✅ POST `/categories/metrics/recompute`
  - 入参：`{"since_date":"2025-05-01","rebuild":true}`
  - 用途：离线重算分类聚合（权限控制）。

- ✅ GET `/admin/metrics/timeseries`
  - 参数：`?metric=topics_new_per_day&days=30`
  - 出参：时间序列点列（date, value）。
  - 支持的指标：`topics_new_per_day`, `topics_total_per_day`, `topics_active_per_day`, `topics_ended_per_day`

- ❌ GET `/admin/token-usage`
  - 状态：**未实现** - Token统计功能待实现
  - 参数：`?group_by=provider|task&since=...`
  - 出参：token 计量与估算成本。

## 字段与计算约定

### 热度归一化（Heat Normalization）
- **触发时机**：每次新事件归并时执行（08:05 / 12:05 / 18:05 / 22:05，Asia/Shanghai）
- **归一化步骤**：
  1. 平台内 Min-Max 归一化：`normalized = (value - min) / (max - min)`
  2. 平台权重加权：`weighted = normalized * platform_weight`
  3. 全局归一化：`heat_normalized = weighted / sum(all_weighted)`，半日内所有事件热度和为 1.0
- **平台权重**：weibo(1.2), zhihu(1.1), baidu(1.1), toutiao(1.0), netease(0.9), sina(0.8), hupu(0.8)
- **特殊处理**：sina/hupu 无热度值，默认赋值 0.5（中等热度）

### 半日归并（Halfday Merge）
- **清晨（MORN）**：8:00 一次采集，08:05 触发归并
- **上午（AM）**：10:00、12:00 两次采集，12:05 触发归并
- **下午（PM）**：14:00、16:00、18:00 三次采集，18:05 触发归并
- **傍晚（EVE）**：20:00、22:00 两次采集，22:05 触发归并
- **筛选规则**：半日内出现次数 ≥2 的事件保留，=1 的事件视为噪音丢弃
- **保留率**：`keep_rate = kept_items / input_items`
- **丢弃率**：`drop_rate = dropped_items / input_items`
- **平均出现次数**：`avg_occurrence = sum(occurrence_count) / merge_groups`

### 整体归并（Global Merge）
- **触发时机**：08:20 / 12:20 / 18:20 / 22:20（新事件归并后约 15 分钟）
- **相似度判定**：向量相似度 > 0.80 召回候选，LLM 判定置信度 > 0.75 确认关联
- **Merge 率**：`merge_rate = merge_count / (merge_count + new_count)`
- **决策**：
  - Merge：归入已有主题，追加 topic_node
  - New：创建新主题

### 其他指标
- **Intensity**：不做平台权重与去水，直接累加覆盖量（与互动量区分存储）。
- **Length**：`length_display` 在服务端按自然日差格式化为 `x天x小时`。
- **分类统计**：
  - 窗口默认 30 天（可配置）；支持 `ended_only=true` 仅统计已结束话题。
  - 平均/最短/最长按 `last_active - first_seen` 计算（小时为基准，前端展示时人性化）。
- **归并拒绝率**：`1 - (判定通过数 / 判定总数)`；统计窗口可配置（默认近 24h）。
- **对话引用命中率**：`有 citations 的回答 / 总回答`。
- **延迟 P95**：滑动窗口计算（如近 24h）。

## 速率限制与错误码

- 速率限制：按 `ip/token` 桶限流（429 返回 Retry-After）。
- 常见错误：
  - 400 INVALID_ARGUMENT（参数缺失/非法）
  - 401 UNAUTHORIZED（鉴权失败）
  - 403 FORBIDDEN（权限不足）
  - 404 NOT_FOUND（资源不存在）
  - 409 CONFLICT（幂等冲突）
  - 429 RATE_LIMITED（超过限额）
  - 500 INTERNAL（服务内部错误）

---

## API实现状态总结

### ✅ 已完成的API（15个）

#### 基础功能
- `GET /health` - 健康检查

#### 采集管理
- `POST /ingest/run` - 触发采集
- `GET /ingest/runs` - 采集历史
- `GET /ingest/sources/status` - 平台状态

#### 话题管理
- `GET /topics` - 话题列表
- `GET /topics/{topic_id}` - 话题详情
- `GET /topics/{topic_id}/timeline` - 时间线

#### 分类统计
- `GET /categories` - 分类列表
- `GET /categories/metrics/summary` - 分类统计摘要
- `GET /categories/metrics/timeseries` - 分类时序数据
- `POST /categories/metrics/recompute` - 重算分类指标

#### 管理后台
- `GET /admin/metrics/summary` - 系统指标（部分）
- `GET /admin/metrics/timeseries` - 管理时序数据

#### 对话功能
- `POST /chat/ask` - RAG对话（非流式）
- `POST /chat/create` - 创建会话

### ✅ 最近完成的API（1个）

#### 对话功能 - SSE流式对话 ⚡️
- `POST /chat/ask` (流式版本) - **SSE流式对话** 
  - 优先级：**P0 - 核心功能**
  - 状态：✅ 已完成并测试通过
  - 技术方案：基于SSE (Server-Sent Events)
  - 后端实现：`backend/app/api/v1/chat.py`, `backend/app/services/rag_service.py`
  - 前端集成：`frontend/src/services/sse.ts`
  - 测试脚本：`backend/test_sse_stream.py`
  - 集成文档：[SSE集成指南](./sse-integration-guide.md)

### ❌ 未实现且不需要的API（10个）

以下API已确认不需要实现：

#### 不需要的功能
- `GET /topics/{topic_id}/heat-trend` - 热度趋势（前端无需求）
- `GET /search/topics` - 向量搜索（可用关键词搜索替代）
- `GET /llm/providers` - LLM配置（已通过文件配置实现）
- `PUT /llm/config` - LLM配置更新（已通过文件配置实现）
- `GET /monitoring/health` - 监控健康检查（暂不实现）
- `GET /monitoring/metrics` - Prometheus指标（暂不实现）
- `GET /monitoring/metrics/summary` - 指标摘要（暂不实现）
- `POST /monitoring/metrics/update` - 更新指标（暂不实现）
- `GET /admin/token-usage` - Token统计（暂不实现）
- `GET /debug/source-items` - 调试接口（不需要）

### 📊 实现进度

- **核心API数**: 16个
- **已完成**: 16个 (100%) ✅
- **开发中**: 0个
- **核心功能完成度**: 100% ✅

### 🎯 前端对接说明

前端当前使用的API路径已修正：
1. ✅ `GET /api/v1/topics` - 热点列表
2. ✅ `GET /api/v1/categories/metrics/summary` - 分类统计
3. ✅ `GET /api/v1/topics/{id}` - 主题详情
4. ✅ `GET /api/v1/topics/{id}/timeline` - 时间线
5. ✅ `POST /api/v1/chat/ask` (流式) - SSE流式对话 ⚡️

所有API路径都使用 `/api/v1` 前缀（由配置项 `VITE_API_BASE_URL` 控制）。

**SSE流式对话集成**：
- 前端代码：`frontend/src/services/sse.ts`
- 使用文档：[SSE集成指南](./sse-integration-guide.md)
- 测试状态：✅ 已通过

### ⚙️ LLM配置说明

LLM配置通过后端配置文件管理，不需要API接口：
- 配置文件：`backend/env.template`
- 配置项：`LLM_PROVIDER`, `LLM_MODEL`, `EMBEDDING_MODEL` 等
- 修改后需重启后端服务生效
