# 回滚到批量归并模式 (AM/PM)

## 📋 回滚概述

**日期**: 2025-11-07  
**操作**: 从实时归并模式（每天8次）回滚到批量归并模式（每天2次）  
**原因**: 根据用户需求，恢复到之前的AM/PM批量归并策略

## 🔄 变更内容

### 1. Period 格式变更

**之前（小时级）**:
```
2025-11-07_08, 2025-11-07_10, ..., 2025-11-07_22
```

**之后（半日级）**:
```
2025-11-07_AM, 2025-11-07_PM
```

### 2. 采集调度变更

| 维度 | 实时模式 (之前) | 批量模式 (之后) |
|------|----------------|----------------|
| **采集频率** | 8次/天 | 8次/天 |
| **采集时间** | 8:00, 10:00, 12:00, 14:00, 16:00, 18:00, 20:00, 22:00 | 8:00, 10:00, 12:00, 14:00, 16:00, 18:00, 20:00, 22:00 |
| **时段划分** | 每2小时一个时段 | AM (8:00-12:00), PM (14:00-22:00) |

### 3. 归并调度变更

| 阶段 | 实时模式 (之前) | 批量模式 (之后) |
|------|----------------|----------------|
| **阶段一** | 8次/天（XX:15） | 2次/天（12:15, 22:15） |
| **阶段二** | 8次/天（XX:30） | 2次/天（12:30, 22:30） |
| **数据延迟** | ~30分钟 | ~15-30分钟 |

### 4. 修改的文件

#### Backend (5个文件)

1. **`backend/app/services/heat_normalization.py`**
   - `calculate_halfday_period()`: 从小时级改回AM/PM
   ```python
   # 之前
   period = f"{dt.hour:02d}"
   
   # 之后
   period = "AM" if dt.hour < 14 else "PM"
   ```

2. **`backend/app/services/ingestion/ingestion_service.py`**
   - Period计算逻辑同上

3. **`backend/app/tasks/celery_app.py`**
   - 采集任务：保持8次（8:00-22:00，每2小时）
   - 归并任务：删除16个小时级任务，恢复4个批量任务
   ```python
   # 采集：8:00-22:00，每2小时
   "ingest-scheduled": crontab(hour="8,10,12,14,16,18,20,22", minute=0)
   
   # 归并阶段一：12:15 & 22:15
   "halfday-merge-am": crontab(hour=12, minute=15)
   "halfday-merge-pm": crontab(hour=22, minute=15)
   
   # 归并阶段二：12:30 & 22:30
   "global-merge-am": crontab(hour=12, minute=30)
   "global-merge-pm": crontab(hour=22, minute=30)
   ```

4. **`backend/app/tasks/merge_tasks.py`**
   - 删除 `period: str = None` 参数
   - 简化为自动判断当前时段
   ```python
   # 之前
   def halfday_merge(period: str = None):
       ...
       await run_halfday_merge_async(period)
   
   # 之后
   def halfday_merge():
       ...
       await run_halfday_merge_async()
   ```

5. **`docs/experiment.txt`**
   - 更新调度和period格式说明

#### Frontend (1个文件)

6. **`frontend/src/pages/HomePage.tsx`**
   - 采集时间显示：保持 "8:00-22:00 每2小时采集"

## 📊 对比总结

| 指标 | 实时模式 | 批量模式 |
|------|---------|---------|
| **采集次数** | 8次/天 | 8次/天 |
| **归并次数** | 16次/天 | 4次/天 |
| **数据延迟** | ~30分钟 | ~15-30分钟 |
| **Period粒度** | 小时级 | 半日级 |
| **LLM调用** | 分散，小批量 | 集中，大批量 |
| **系统负载** | 持续运行 | 峰值集中 |
| **数据新鲜度** | 高 | 高 |

## ✅ 回滚步骤

1. ✅ 修改 `heat_normalization.py` 的 period 计算逻辑
2. ✅ 修改 `ingestion_service.py` 的 period 计算逻辑
3. ✅ 修改 `celery_app.py` 的调度配置
4. ✅ 修改 `merge_tasks.py` 的函数签名和参数处理
5. ✅ 修改 `HomePage.tsx` 的前端显示
6. ✅ 重启 Celery Beat 和 Worker
7. ✅ 更新 `experiment.txt` 文档

## 🎯 验证要点

- [ ] 确认今天12:00能正常触发采集任务
- [ ] 确认今天12:15和12:30能正常触发归并任务
- [ ] 检查新采集数据的 `halfday_period` 格式为 `YYYY-MM-DD_AM` 或 `YYYY-MM-DD_PM`
- [ ] 前端页面显示 "8:00-22:00 每2小时采集"

## 📝 注意事项

1. **历史数据兼容性**:
   - 之前小时级的period数据（如 `2025-11-07_10`）仍然保留在数据库中
   - 这些数据不会影响新的批量归并流程
   - 如需清理，可以手动执行数据迁移

2. **下次任务时间**:
   - 今天 12:00 - 采集任务（1小时后）
   - 今天 12:15 - 归并阶段一（1小时15分钟后）
   - 今天 12:30 - 归并阶段二（1小时30分钟后）
   - 今晚 14:00-22:00 - 每2小时采集
   - 今晚 22:15 - 归并阶段一
   - 今晚 22:30 - 归并阶段二

3. **服务状态**:
   - Celery Beat: 运行中
   - Celery Worker: 运行中 (13个进程)
   - FastAPI: 运行中

## 🔙 如需再次切换回实时模式

参考 `docs/REALTIME_MERGE_MIGRATION.md` 进行反向操作。

---

**回滚完成时间**: 2025-11-07 11:01  
**执行人**: AI Assistant  
**状态**: ✅ 完成

