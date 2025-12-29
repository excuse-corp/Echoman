# 前端数据更新流程说明

## 概述

Echoman 前端通过**轮询 REST API** 的方式获取后端数据更新，无需 WebSocket 或 SSE 推送。

## 数据流转全链路

```
┌─────────────────────────────────────────────────────────────────────┐
│ 后端数据处理流程                                                     │
└─────────────────────────────────────────────────────────────────────┘

08:00-22:00  → 采集任务（每2小时）
每2小时        └─ SourceItems 表插入新数据
                 ├─ status: pending_halfday_merge
                 └─ halfday_period: 2025-11-04_AM/PM

     ↓

12:05/18:05/22:05  → 【归并阶段一】新事件归并任务
               ├─ 热度归一化
               ├─ 向量聚类
               ├─ LLM判定
               ├─ 出现次数筛选（≥2次保留）
               └─ 更新 SourceItems
                  ├─ 保留: status → pending_global_merge
                  └─ 丢弃: status → discarded

     ↓

12:20/18:20/22:20  → 【归并阶段二】整体归并任务
               ├─ 向量检索历史Topics
               ├─ LLM关联判定
               ├─ 决策: merge（归入已有主题）or new（创建新主题）
               └─ 数据库写入：
                  ├─ Topics 表：新建或更新主题 ✅
                  ├─ TopicNodes 表：记录主题-源数据关联 ✅
                  ├─ TopicHalfdayHeat 表：记录半日热度 ✅
                  └─ SourceItems：status → merged ✅

     ↓

前端API轮询  → GET /api/v1/topics
               └─ 前端页面显示最新热点数据

┌─────────────────────────────────────────────────────────────────────┐
│ 前端数据获取流程                                                     │
└─────────────────────────────────────────────────────────────────────┘

用户访问页面
     ↓
useEffect() 初始化
     ↓
调用 getHotspots() → GET /api/v1/topics
     ↓
显示热点列表
     ↓
用户选择热点
     ↓
调用 getTopicDetail() → GET /api/v1/topics/{id}
调用 getTimeline() → GET /api/v1/topics/{id}/timeline
     ↓
显示热点详情和时间线
```

## 前端数据更新机制

### 当前实现：页面加载时获取

```typescript
// frontend/src/pages/ExplorerPage.tsx
useEffect(() => {
  let cancel = false;
  getHotspots().then(({ items, fallback }) => {
    if (cancel) return;
    setHotspots(items);
    setUsingFallback(fallback);
  });
  return () => {
    cancel = true;
  };
}, []); // 空依赖数组 → 仅在组件挂载时执行一次
```

**特点**：
- ✅ 简单，无额外网络负担
- ❌ 不会自动刷新，需要手动刷新页面

### 升级方案：定时轮询（可选）

如果需要自动刷新数据，可以添加定时轮询：

```typescript
useEffect(() => {
  let cancel = false;
  
  // 立即获取一次
  const fetchData = () => {
    getHotspots().then(({ items, fallback }) => {
      if (cancel) return;
      setHotspots(items);
      setUsingFallback(fallback);
    });
  };
  
  fetchData();
  
  // 每5分钟轮询一次
  const interval = setInterval(fetchData, 5 * 60 * 1000);
  
  return () => {
    cancel = true;
    clearInterval(interval);
  };
}, []);
```

**轮询频率建议**：
- 归并任务执行时间：12:05-12:20、18:05-18:20、22:05-22:20（北京时间/Asia/Shanghai）
- 轮询间隔：5-10分钟（平衡及时性和服务器压力）
- 或者：仅在归并时段（12:00-12:45, 22:00-22:45）加密轮询（1分钟），其他时段不轮询

## 数据库入库验证

### 归并结果入库检查

```bash
# 检查 Topics 表
SELECT COUNT(*) FROM topics;
SELECT * FROM topics ORDER BY created_at DESC LIMIT 5;

# 检查 TopicNodes 表（主题-源数据关联）
SELECT COUNT(*) FROM topic_nodes;
SELECT * FROM topic_nodes ORDER BY appended_at DESC LIMIT 5;

# 检查 TopicHalfdayHeat 表（半日热度快照）
SELECT COUNT(*) FROM topic_halfday_heat;
SELECT * FROM topic_halfday_heat ORDER BY date DESC, created_at DESC LIMIT 5;

# 检查数据完整性
SELECT 
  (SELECT COUNT(*) FROM source_items WHERE merge_status = 'merged') AS merged_items,
  (SELECT COUNT(*) FROM topic_nodes) AS topic_nodes,
  CASE 
    WHEN (SELECT COUNT(*) FROM source_items WHERE merge_status = 'merged') = 
         (SELECT COUNT(*) FROM topic_nodes)
    THEN '✅ 一致'
    ELSE '❌ 不一致'
  END AS integrity_check;
```

### 最新测试结果（2025-11-04）

```
📌 Topics 表: 32 条记录
   - 已正常入库，包含标题、分类、状态等字段

🔗 TopicNodes 表: 67 条记录
   - 记录了主题与源数据的关联关系

🔥 TopicHalfdayHeat 表: 32 条记录
   - 记录了每个主题在各半日时段的热度快照

📊 SourceItems 归并状态:
   - pending_halfday_merge: 1763 条（待阶段一处理）
   - pending_global_merge: 17 条（待阶段二处理）
   - merged: 67 条（已归并）
   - discarded: 381 条（噪音数据）

✅ 数据完整性检查通过：merged items 与 TopicNodes 数量一致
```

## API 端点说明

### 1. 获取热点列表

```http
GET /api/v1/topics
```

**响应示例**：
```json
{
  "items": [
    {
      "topic_id": "60",
      "title": "山姆在争议声中再更新APP",
      "summary": "...",
      "intensity_raw": 2,
      "intensity_norm": 100.0,
      "length_days": 0.0,
      "first_seen": "2025-11-04T09:02:33",
      "last_active": "2025-11-04T09:02:33",
      "platforms": ["weibo", "zhihu"],
      "platform_mentions": {...},
      "status": "active"
    }
  ]
}
```

### 2. 获取热点详情

```http
GET /api/v1/topics/{topic_id}
```

### 3. 获取热点时间线

```http
GET /api/v1/topics/{topic_id}/timeline
```

## 数据更新时间表（北京时间）

| 时间 | 任务 | 说明 |
|------|------|------|
| 08:00 | 采集任务 #1 | 爬取各平台热点 |
| 10:00 | 采集任务 #2 | |
| 12:00 | 采集任务 #3 | |
| **12:05** | **归并阶段一（AM）** | 对8:00-12:00的数据去噪 |
| **12:20** | **归并阶段二（AM）** | 与历史Topic比对，更新数据库 ✅ |
| 14:00 | 采集任务 #4 | |
| 16:00 | 采集任务 #5 | |
| 18:00 | 采集任务 #6 | |
| 20:00 | 采集任务 #7 | |
| 22:00 | 采集任务 #8 | |
| **18:05** | **归并阶段一（PM）** | 对14:00-18:00的数据去噪 |
| **18:20** | **归并阶段二（PM）** | 与历史Topic比对，更新数据库 ✅ |
| **22:05** | **归并阶段一（EVE）** | 对20:00-22:00的数据去噪 |
| **22:20** | **归并阶段二（EVE）** | 与历史Topic比对，更新数据库 ✅ |

**前端数据更新时机**：
- 当前：页面加载时获取一次
- 建议：在 12:20-12:35 / 18:20-18:35 / 22:20-22:35 期间增加轮询频率（如1分钟）
- 其他时段：保持当前策略或降低轮询频率（如5-10分钟）

## 前端fallback机制

当后端API不可用时，前端会使用内置的模拟数据（fallback data）：

```typescript
// frontend/src/services/api.ts
export async function getHotspots(): Promise<{ items: HotspotSummary[]; fallback: boolean }> {
  try {
    const response = await fetch(`${API_BASE_URL}/topics`);
    if (!response.ok) {
      throw new Error(`Bad status: ${response.status}`);
    }
    const payload = await response.json();
    return { items: payload.items as HotspotSummary[], fallback: false };
  } catch (error) {
    console.warn("[api] getHotspots fallback, reason:", error);
    return { items: fallbackHotspots, fallback: true }; // 使用内置模拟数据
  }
}
```

## 总结

### 数据流转
1. **采集** → SourceItems 表（pending_halfday_merge）
2. **阶段一** → 去噪筛选 → SourceItems（pending_global_merge 或 discarded）
3. **阶段二** → 归并决策 → **Topics/TopicNodes/TopicHalfdayHeat 表更新** ✅
4. **前端** → 通过 API 轮询获取最新数据

### 前端更新方式
- **当前**：页面加载时获取一次（简单、低负担）
- **可选升级**：定时轮询（5-10分钟）或智能轮询（归并时段密集轮询）

### 数据库入库
- ✅ Topics 表：已正常入库
- ✅ TopicNodes 表：已正常入库
- ✅ TopicHalfdayHeat 表：已正常入库
- ✅ 数据完整性验证：通过

归并流程完整，数据流转正常！🎉

