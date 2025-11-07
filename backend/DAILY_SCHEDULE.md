# 📅 Echoman 每日任务调度规划

> 基于代码分析：`backend/app/tasks/celery_app.py`

---

## 📊 任务调度总览

### 每日任务类型
1. **采集任务**：8次/天（每2小时）
2. **归并任务**：6次/天（3个周期×2阶段）
3. **统计任务**：1次/天（凌晨）

**总计**：15个定时任务/天

---

## 🕐 每日时间表

### 采集任务（8次）

| 时间 | 任务 | 周期 | 说明 |
|------|------|------|------|
| **08:00** | 采集 #1 | AM | 上午周期开始 |
| **10:00** | 采集 #2 | AM | 上午周期中 |
| **12:00** | 采集 #3 | AM | 上午周期结束 |
| **14:00** | 采集 #4 | PM | 下午周期开始 |
| **16:00** | 采集 #5 | PM | 下午周期中 |
| **18:00** | 采集 #6 | PM | 下午周期结束 |
| **20:00** | 采集 #7 | EVE | 傍晚周期开始 |
| **22:00** | 采集 #8 | EVE | 傍晚周期结束 |

**Crontab 配置**：
```python
crontab(hour="8,10,12,14,16,18,20,22", minute=0)
```

**任务函数**：`app.tasks.ingestion_tasks.scheduled_ingestion`

---

### 归并任务（6次 = 3周期 × 2阶段）

#### 上午归并周期（AM）

| 时间 | 阶段 | 任务 | 说明 |
|------|------|------|------|
| **12:15** | 阶段一 | 新事件归并 | 处理 8:00/10:00/12:00 采集数据 |
| **12:30** | 阶段二 | 全局归并 | 关联演进，生成/更新主题 |

**处理数据**：AM 时段（8:00、10:00、12:00）的3次采集结果

**Crontab 配置**：
```python
# 阶段一
"halfday-merge-am": crontab(hour=12, minute=15)
# 阶段二
"global-merge-am": crontab(hour=12, minute=30)
```

---

#### 下午归并周期（PM）

| 时间 | 阶段 | 任务 | 说明 |
|------|------|------|------|
| **18:15** | 阶段一 | 新事件归并 | 处理 14:00/16:00/18:00 采集数据 |
| **18:30** | 阶段二 | 全局归并 | 关联演进，生成/更新主题 |

**处理数据**：PM 时段（14:00、16:00、18:00）的3次采集结果

**Crontab 配置**：
```python
# 阶段一
"halfday-merge-pm": crontab(hour=18, minute=15)
# 阶段二
"global-merge-pm": crontab(hour=18, minute=30)
```

---

#### 傍晚归并周期（EVE）

| 时间 | 阶段 | 任务 | 说明 |
|------|------|------|------|
| **22:15** | 阶段一 | 新事件归并 | 处理 20:00/22:00 采集数据 |
| **22:30** | 阶段二 | 全局归并 | 关联演进，生成/更新主题 |

**处理数据**：EVE 时段（20:00、22:00）的2次采集结果

**Crontab 配置**：
```python
# 阶段一
"halfday-merge-eve": crontab(hour=22, minute=15)
# 阶段二
"global-merge-eve": crontab(hour=22, minute=30)
```

---

### 统计任务（1次）

| 时间 | 任务 | 说明 |
|------|------|------|
| **01:00** | 分类统计重算 | 重算一年窗口的分类统计指标 |

**Crontab 配置**：
```python
"daily-recompute-category-metrics": crontab(hour=1, minute=0)
```

**任务函数**：`app.tasks.category_metrics_tasks.daily_recompute_metrics`

---

## 📈 完整时间轴（单日）

```
00:00 ─────────────────────────────────────────────────
01:00 ⚙️  【分类统计重算】
      │
08:00 📥 【采集 #1】────┐
      │                 │
10:00 📥 【采集 #2】    │ AM 周期（3次采集）
      │                 │
12:00 📥 【采集 #3】────┘
12:15 🔄 【上午归并 - 阶段一】新事件归并（去噪过滤）
12:30 🔄 【上午归并 - 阶段二】全局归并（关联演进）
      │
14:00 📥 【采集 #4】────┐
      │                 │
16:00 📥 【采集 #5】    │ PM 周期（3次采集）
      │                 │
18:00 📥 【采集 #6】────┘
18:15 🔄 【下午归并 - 阶段一】新事件归并（去噪过滤）
18:30 🔄 【下午归并 - 阶段二】全局归并（关联演进）
      │
20:00 📥 【采集 #7】────┐
      │                 │ EVE 周期（2次采集）
22:00 📥 【采集 #8】────┘
22:15 🔄 【傍晚归并 - 阶段一】新事件归并（去噪过滤）
22:30 🔄 【傍晚归并 - 阶段二】全局归并（关联演进）
      │
23:59 ─────────────────────────────────────────────────
```

---

## 🔍 任务细节

### 采集任务（scheduled_ingestion）

**配置位置**：`backend/app/tasks/celery_app.py` 第52-59行

```python
"ingest-scheduled": {
    "task": "app.tasks.ingestion_tasks.scheduled_ingestion",
    "schedule": crontab(
        hour="8,10,12,14,16,18,20,22",
        minute=0
    ),
}
```

**任务逻辑**：
- 调用 `IngestionService.run_ingestion()`
- 从配置的平台（微博、知乎、头条等）抓取热榜数据
- 默认每平台抓取30条
- 数据写入 `source_items` 表，状态为 `pending_event_merge`

---

### 归并任务（halfday_merge + global_merge）

**配置位置**：`backend/app/tasks/celery_app.py` 第61-91行

#### 阶段一：新事件归并（halfday_merge）

**任务函数**：`app.tasks.merge_tasks.halfday_merge`
**服务类**：`EventMergeService`（已重命名）

**职责**：
1. 热度归一化（归并周期内）
2. 相似度聚类（找出重复/相似事件）
3. 出现次数过滤（occurrence_count < 2 的丢弃）
4. 更新状态：`pending_event_merge` → `pending_global_merge` 或 `discarded`

#### 阶段二：全局归并（global_merge）

**任务函数**：`app.tasks.merge_tasks.global_merge`
**服务类**：`GlobalMergeService`

**职责**：
1. LLM判断（是否真实事件，提取标签）
2. 向量检索（找相似历史主题）
3. 主题关联（新增或更新主题）
4. 计算演进类型（NEW/UPDATE/HEAT）
5. 生成 TopicSnapshot 和 TopicPeriodHeat
6. 更新状态：`pending_global_merge` → `merged`

---

### 统计任务（daily_recompute_metrics）

**配置位置**：`backend/app/tasks/celery_app.py` 第96-99行

**任务函数**：`app.tasks.category_metrics_tasks.daily_recompute_metrics`

**职责**：
- 重算各分类的统计指标（一年时间窗口）
- 更新 `CategoryMetrics` 表
- 计算回声强度、共鸣频率、持续性等

---

## 📊 数据流转

```
┌──────────────┐
│ 采集任务      │ scheduled_ingestion (8次/天)
│ 8-22点,偶数小时│
└──────┬───────┘
       │ 写入
       ↓
┌──────────────────────────────────────────┐
│ source_items 表                           │
│ status: pending_event_merge              │
│ period: 2025-11-07_AM/PM/EVE             │
└──────┬───────────────────────────────────┘
       │ 12:15/18:15/22:15 触发
       ↓
┌──────────────────────────────────────────┐
│ 【归并阶段一】新事件归并                    │
│ EventMergeService.run_event_merge()      │
│ - 热度归一化                              │
│ - 相似度聚类                              │
│ - 出现次数过滤                            │
└──────┬───────────────────────────────────┘
       │ status → pending_global_merge
       │ 12:30/18:30/22:30 触发
       ↓
┌──────────────────────────────────────────┐
│ 【归并阶段二】全局归并                     │
│ GlobalMergeService.run_global_merge()    │
│ - LLM 真实性判断                          │
│ - 向量检索历史主题                        │
│ - 主题关联（新增/更新）                   │
└──────┬───────────────────────────────────┘
       │ status → merged
       ↓
┌──────────────────────────────────────────┐
│ topics 表 + topic_snapshots 表            │
│ + topic_period_heat 表                    │
│                                           │
│ 最终输出：主题快照 + 演进历史              │
└───────────────────────────────────────────┘
```

---

## 🎯 关键设计点

### 1. 三周期归并设计

**为什么是 AM/PM/EVE 三个周期？**

- **AM（上午）**：8-12点，3次采集，捕捉早间热点
- **PM（下午）**：14-18点，3次采集，捕捉午后热点
- **EVE（傍晚）**：20-22点，2次采集，捕捉晚间热点

**优势**：
- 更及时的热点响应（每6-8小时一次归并）
- 热度归一化更准确（同一时段内的数据具有可比性）
- 避免跨时段的热度差异（早晚热度基准不同）

### 2. 两阶段归并设计

**阶段一（新事件归并）**：去噪过滤
- 过滤单次出现的噪音数据
- 保留在周期内多次出现的真实热点

**阶段二（全局归并）**：关联演进
- 通过 LLM 验证真实性
- 通过向量检索关联历史主题
- 生成主题演进快照

**时间间隔**：15分钟
- 阶段一：12:15/18:15/22:15
- 阶段二：12:30/18:30/22:30
- 确保阶段一完成后再执行阶段二

### 3. 热度归一化设计

**归一化范围 = 归并周期**
- AM 周期：8:00/10:00/12:00 的所有数据一起归一化
- PM 周期：14:00/16:00/18:00 的所有数据一起归一化
- EVE 周期：20:00/22:00 的所有数据一起归一化

**归一化结果**：
- 每个周期内所有事件的 `heat_normalized` 之和 = 1.0
- 便于周期内事件热度对比

---

## 📝 配置参数

### 采集参数
- **频率**：每2小时
- **时间范围**：8:00-22:00（14小时）
- **次数**：8次/天
- **每平台抓取量**：30条（默认）

### 归并参数
- **周期数**：3个（AM/PM/EVE）
- **阶段数**：2个（新事件归并 + 全局归并）
- **总次数**：6次/天（3×2）
- **出现次数阈值**：≥2（过滤单次出现）

### Celery 配置
- **时区**：Asia/Shanghai
- **任务超时**：1小时（硬限制）
- **软超时**：50分钟
- **并发数**：8（可配置）
- **单Worker最大任务数**：1000

---

## 🔧 相关文件

### 任务调度
- `backend/app/tasks/celery_app.py` - Celery Beat 配置
- `backend/app/tasks/ingestion_tasks.py` - 采集任务实现
- `backend/app/tasks/merge_tasks.py` - 归并任务实现

### 服务逻辑
- `backend/app/services/ingestion.py` - 采集服务
- `backend/app/services/event_merge.py` - 新事件归并服务
- `backend/app/services/global_merge.py` - 全局归并服务
- `backend/app/services/heat_normalization.py` - 热度归一化服务

### 数据模型
- `backend/app/models/source_item.py` - 采集数据模型
- `backend/app/models/topic.py` - 主题相关模型

---

## 📊 监控建议

### 关键时间点
- **12:15/12:30** - 上午归并
- **18:15/18:30** - 下午归并（新增）
- **22:15/22:30** - 傍晚归并

### 监控指标
```bash
# 查看 Celery Beat 日志
tail -f /root/ren/Echoman/backend/celery_beat.log

# 查看 Celery Worker 日志
tail -f /root/ren/Echoman/backend/celery_worker.log

# 查看 API 日志
tail -f /root/ren/Echoman/backend/uvicorn.log
```

### 数据验证
```sql
-- 查看今日采集数据按周期分布
SELECT period, COUNT(*) 
FROM source_items 
WHERE DATE(fetched_at) = CURRENT_DATE 
GROUP BY period 
ORDER BY period;

-- 查看今日归并结果
SELECT date, period, COUNT(*) 
FROM topic_period_heat 
WHERE date = CURRENT_DATE 
GROUP BY date, period 
ORDER BY period;
```

---

**文档生成时间**：2025-11-07  
**系统版本**：v0.1.0  
**部署状态**：✅ 已部署，三周期模式已激活


