# 三周期归并重构 - 数据库变更说明

## 变更概述

将系统从**每日2次归并**升级为**每日3次归并**（上午、下午、傍晚）。

## 变更内容

### 1. 数据库模型更新

#### `topic_halfday_heat` 表
- **字段**：`period` (String(10))
- **变更前**：仅支持 "AM"、"PM"
- **变更后**：支持 "AM"、"PM"、"EVE"
- **影响**：✅ 无需迁移（字段长度已足够）

#### `source_items` 表
- **字段**：`halfday_period` (String(20))
- **变更**：注释更新，字段本身无变化
- **影响**：✅ 无需迁移

### 2. 业务逻辑更新

#### 归并周期划分
- **上午（AM）**：8:00-12:00 的采集（3次）→ 12:15归并
- **下午（PM）**：14:00-18:00 的采集（3次）→ 18:15归并
- **傍晚（EVE）**：20:00-22:00 的采集（2次）→ 22:15归并

#### Celery 调度更新
```python
# 新增下午归并任务
"halfday-merge-pm": {
    "task": "app.tasks.merge_tasks.halfday_merge",
    "schedule": crontab(hour=18, minute=15),  # 从 22:15 改为 18:15
},

# 新增傍晚归并任务
"halfday-merge-eve": {
    "task": "app.tasks.merge_tasks.halfday_merge",
    "schedule": crontab(hour=22, minute=15),  # 新增
},
```

## 数据兼容性

### 现有数据
- ✅ 数据库中现有的 "AM" 和 "PM" 记录保持不变
- ✅ 新的 "EVE" 记录将在首次傍晚归并后自动产生
- ✅ 所有字段长度足够容纳新值

### 数据迁移
**❌ 不需要数据迁移脚本**

理由：
1. 字段类型和长度没有变化
2. 现有数据完全兼容
3. 新周期数据会自然产生

## 部署步骤

### 1. 停止服务
```bash
# 停止 Celery Beat（调度器）
sudo systemctl stop celery_beat

# 停止 Celery Worker
sudo systemctl stop celery_worker

# 停止 API 服务
sudo systemctl stop echoman_api
```

### 2. 更新代码
```bash
cd /root/ren/Echoman
git pull origin main
```

### 3. 重启服务
```bash
# 启动 API 服务
sudo systemctl start echoman_api

# 启动 Celery Worker
sudo systemctl start celery_worker

# 启动 Celery Beat（新调度将生效）
sudo systemctl start celery_beat
```

### 4. 验证部署
```bash
# 查看 Celery Beat 日志，确认新任务已注册
tail -f /root/ren/Echoman/backend/celery_beat.log | grep -E "halfday-merge|global-merge"

# 应该看到 6 个归并任务：
# - halfday-merge-am (12:15)
# - global-merge-am (12:30)
# - halfday-merge-pm (18:15)  # 新时间
# - global-merge-pm (18:30)   # 新时间
# - halfday-merge-eve (22:15) # 新任务
# - global-merge-eve (22:30)  # 新任务
```

## 回滚方案

如需回滚到两周期模式：

### 1. 代码回滚
```bash
git revert <commit-hash>
```

### 2. 手动调整（如果需要）
编辑 `backend/app/services/heat_normalization.py`：
```python
def calculate_halfday_period(self, dt: datetime = None) -> str:
    # 恢复两周期逻辑
    if dt.hour < 14:
        period = "AM"
    else:
        period = "PM"  # 14点后都是PM
    return f"{date_str}_{period}"
```

### 3. 重启服务
```bash
sudo systemctl restart celery_beat celery_worker echoman_api
```

## 监控指标

### 关键指标
- 每日归并次数：从 2 次增加到 3 次
- 单次归并数据量：
  - AM: ~180-270条（3次采集）
  - PM: ~180-270条（3次采集）
  - EVE: ~120-180条（2次采集）
  
### 预期效果
- ✅ 数据时效性提升：最长延迟从10小时降至4小时
- ✅ 负载更均衡：避免晚上10点处理大量数据
- ✅ 事件追踪更精准：更细粒度的时间线

## 相关文档

- [merge-logic.md](/root/ren/Echoman/docs/merge-logic.md): 归并逻辑详解
- [ECHO_METRICS_CALCULATION.md](/root/ren/Echoman/docs/ECHO_METRICS_CALCULATION.md): 回声指标计算

## 变更记录

| 日期 | 变更内容 | 负责人 |
|-----|---------|-------|
| 2025-11-07 | 三周期归并重构 | AI Assistant |


