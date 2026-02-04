# 📅 Echoman 每日任务调度

> 基于代码分析：`backend/app/tasks/celery_app.py`
> 更新时间：2026-02-04

---

## 📊 任务总览

- **采集任务**：8 次/天（每 2 小时）
- **归并任务**：8 次/天（4 个周期 × 2 阶段：MORN/AM/PM/EVE）
- **统计任务**：1 次/天（凌晨）

**总计**：17 个定时任务/天

---

## 🕐 每日时间表

### 采集任务（8次）

| 时间 | 任务 | 周期 | 说明 |
|------|------|------|------|
| 08:00 | 采集 #1 | MORN | 早间单次采集 |
| 10:00 | 采集 #2 | AM | 上午周期中 |
| 12:00 | 采集 #3 | AM | 上午周期结束 |
| 14:00 | 采集 #4 | PM | 下午周期开始 |
| 16:00 | 采集 #5 | PM | 下午周期中 |
| 18:00 | 采集 #6 | PM | 下午周期结束 |
| 20:00 | 采集 #7 | EVE | 傍晚周期开始 |
| 22:00 | 采集 #8 | EVE | 傍晚周期结束 |

**Crontab 配置**：
```python
crontab(hour="8,10,12,14,16,18,20,22", minute=0)
```

**任务函数**：`app.tasks.ingestion_tasks.scheduled_ingestion`

---

### 归并任务（8次 = 4周期 × 2阶段）

#### 清晨归并（MORN）

| 时间 | 阶段 | 任务 | 说明 |
|------|------|------|------|
| 08:05 | 阶段一 | 新事件归并 | 处理 08:00 采集数据 |
| 08:20 | 阶段二 | 全局归并 | 关联演进，生成/更新主题 |

#### 上午归并（AM）

| 时间 | 阶段 | 任务 | 说明 |
|------|------|------|------|
| 12:05 | 阶段一 | 新事件归并 | 处理 10:00/12:00 采集数据 |
| 12:20 | 阶段二 | 全局归并 | 关联演进，生成/更新主题 |

#### 下午归并（PM）

| 时间 | 阶段 | 任务 | 说明 |
|------|------|------|------|
| 18:05 | 阶段一 | 新事件归并 | 处理 14:00/16:00/18:00 采集数据 |
| 18:20 | 阶段二 | 全局归并 | 关联演进，生成/更新主题 |

#### 傍晚归并（EVE）

| 时间 | 阶段 | 任务 | 说明 |
|------|------|------|------|
| 22:05 | 阶段一 | 新事件归并 | 处理 20:00/22:00 采集数据 |
| 22:20 | 阶段二 | 全局归并 | 关联演进，生成/更新主题 |

**任务函数**：
- 阶段一：`app.tasks.merge_tasks.halfday_merge`（历史命名，实际为 event_merge）
- 阶段二：`app.tasks.merge_tasks.global_merge`

---

### 统计任务（1次）

| 时间 | 任务 | 说明 |
|------|------|------|
| 01:00 | 分类统计重算 | 重算当日分类统计指标 |

**任务函数**：`app.tasks.category_metrics_tasks.daily_recompute_metrics`

---

## 📈 完整时间轴（单日）

```
00:00 ─────────────────────────────────────────────────
01:00 ⚙️  分类统计重算

08:00 📥 采集 #1 (MORN)
08:05 🔄 归并阶段一 (MORN/event_merge)
08:20 🔄 归并阶段二 (MORN/global_merge)

10:00 📥 采集 #2 (AM)
12:00 📥 采集 #3 (AM)
12:05 🔄 归并阶段一 (AM/event_merge)
12:20 🔄 归并阶段二 (AM/global_merge)

14:00 📥 采集 #4 (PM)
16:00 📥 采集 #5 (PM)
18:00 📥 采集 #6 (PM)
18:05 🔄 归并阶段一 (PM/event_merge)
18:20 🔄 归并阶段二 (PM/global_merge)

20:00 📥 采集 #7 (EVE)
22:00 📥 采集 #8 (EVE)
22:05 🔄 归并阶段一 (EVE/event_merge)
22:20 🔄 归并阶段二 (EVE/global_merge)
23:59 ─────────────────────────────────────────────────
```

---

## 🔍 任务细节

### 采集任务（scheduled_ingestion）

- 入口：`backend/app/tasks/ingestion_tasks.py`
- 服务：`IngestionService`（`backend/app/services/ingestion/ingestion_service.py`）
- 逻辑：
  - 抓取各平台热榜（默认每平台 30 条）
  - 噪音过滤后写入 `source_items`
  - 标记 `merge_status = pending_event_merge` 和 `period`

### 归并任务（event_merge + global_merge）

- 阶段一：`EventMergeService`（`backend/app/services/halfday_merge.py`）
  - 热度归一化（Min-Max + 平台权重）
  - 标题 Jaccard + 向量聚类
  - LLM 判定同组事件
  - 出现次数过滤（默认 ≥2）

- 阶段二：`GlobalMergeService`（`backend/app/services/global_merge.py`）
  - 向量检索候选 topics（优先 topic_summary）
  - LLM 关联判定
  - 更新 topics/topic_nodes/topic_period_heat
  - 触发前端数据刷新（`FrontendUpdateService`）

### 统计任务（daily_recompute_metrics）

- 服务：`CategoryMetricsService`（`backend/app/services/category_metrics_service.py`）
- 结果写入：`category_day_metrics`

---

## 📊 数据验证建议

```sql
-- 今日采集数据按周期分布
SELECT period, COUNT(*)
FROM source_items
WHERE DATE(fetched_at) = CURRENT_DATE
GROUP BY period
ORDER BY period;

-- 今日归并结果
SELECT date, period, COUNT(*)
FROM topic_period_heat
WHERE date = CURRENT_DATE
GROUP BY date, period
ORDER BY period;
```

---

**系统时区**：Asia/Shanghai（UTC+8）
