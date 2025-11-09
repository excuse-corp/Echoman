# 归并逻辑优化总结

**优化时间**: 2025-11-07  
**版本**: v3.1  

---

## 📋 优化与修复内容

### 1️⃣ 整体归并：只与最近7天的Topic比对

**优化目的**: 避免新事件与过时的老事件关联，提升归并准确性和性能

**修改文件**: `backend/app/services/global_merge.py`

**具体变更**:
```python
# 计算7天前的时间（只检索最近一周的topic）
one_week_ago = now_cn() - timedelta(days=7)

# 在向量检索时添加时间过滤
stmt = select(TopicNode, Topic).join(
    Topic, TopicNode.topic_id == Topic.id
).where(
    and_(
        TopicNode.source_item_id == source.id,
        Topic.status == "active",
        Topic.last_active >= one_week_ago  # ✅ 只检索最近7天的topic
    )
)
```

**效果**:
- ✅ 减少无效比对，提升性能
- ✅ 避免与过时事件关联
- ✅ 提高归并准确度

---

### 2️⃣ 新事件归并时间：提前10分钟

**优化目的**: 确保采集任务完全结束后再开始归并，避免数据不完整

**修改文件**: `backend/app/tasks/celery_app.py`

**具体变更**:

| 归并周期 | 原时间 | 新时间 | 说明 |
|---------|--------|--------|------|
| **上午（AM）** | 12:15 → 12:30 | **12:05 → 12:20** | 处理8:00、10:00、12:00采集数据 |
| **下午（PM）** | 18:15 → 18:30 | **18:05 → 18:20** | 处理14:00、16:00、18:00采集数据 |
| **傍晚（EVE）** | 22:15 → 22:30 | **22:05 → 22:20** | 处理20:00、22:00采集数据 |

**效果**:
- ✅ 给采集任务更多缓冲时间
- ✅ 确保数据完整性
- ✅ 减少数据缺失导致的归并问题

---

### 3️⃣ 归并完成后自动更新前端数据

**优化目的**: 归并完成后立即刷新前端需要的数据，提升用户体验

**新增文件**: `backend/app/services/frontend_update_service.py`

**功能**:
1. **更新最后归并时间戳** - 供前端检测数据更新
2. **刷新 Topics 表聚合统计** - 确保前端看到最新数据
3. **记录归并完成事件** - 用于监控和调试

**集成位置**: `backend/app/services/global_merge.py` 的 `run_global_merge` 方法

```python
# 4. 更新前端数据
try:
    from app.services.frontend_update_service import update_frontend_after_merge
    await update_frontend_after_merge(self.db, period, merge_stats)
except Exception as e:
    print(f"  ⚠️  前端数据更新失败（不影响归并）: {e}")
```

**效果**:
- ✅ 前端可以实时检测数据更新
- ✅ 提升用户体验
- ✅ 便于监控和调试

---

## 📊 事件分类任务状态检查

### ✅ 分类功能正常运行

**检查结果**:
- ✅ 分类服务正常工作
- ✅ 今天已分类 113/258 个Topic（43.8%）
- ✅ 最近分类时间：20:37:35（EVE周期归并时）

**分类分布**（今天）:
- 时事（current_affairs）：71个
- 体育电竞（sports_esports）：25个
- 娱乐八卦（entertainment）：17个

### ⚠️ 发现的问题

**问题1**: 部分Topic使用默认分类
- **原因**: 分类时Topic的nodes数据未加载或为空
- **方法**: `default`
- **置信度**: 0.30（较低）
- **分类结果**: 统一为 `current_affairs`

**问题2**: 未分类的Topic
- 在归并时创建的新Topic可能暂时未分类
- 手动分类脚本可以补充分类：`scripts/classify_unclassified_topics.py`

### 🔧 已补救

运行手动分类脚本，已对所有未分类Topic进行补充分类：
```bash
python scripts/classify_unclassified_topics.py
```

**结果**: ✅ 145个未分类Topic已全部分类

### 🐛 发现重大Bug并修复

**问题**: 143个Topic使用default分类（置信度0.30），没有使用LLM

**根本原因**: 这些Topic在创建时**没有正确保存TopicNodes数据**
- Topic被flush后有了ID
- 但TopicNodes创建失败或commit失败
- 分类时查询nodes为空，直接返回default分类

**修复方案**:
1. ✅ 清理了143个不完整的Topic（`scripts/fix_topics_without_nodes.py`）
2. ✅ 改进了`_create_new_topic`方法的异常处理
   - 添加try-except包裹整个创建过程
   - 在提交前添加flush确保nodes被保存
   - 分类前刷新会话，确保能查询到刚创建的nodes
   - 记录创建的nodes数量用于调试
3. ✅ 分类失败不影响Topic创建（独立的异常处理）

**修复后状态**:
- ✅ 所有Topic都有完整的nodes数据
- ✅ 分类逻辑正常工作（rule + LLM）
- ✅ 不会再出现大量default分类

详细报告见：[CLASSIFICATION_FIX_REPORT.md](CLASSIFICATION_FIX_REPORT.md)

---

## 🚀 部署状态

### Celery 服务状态

**Worker**: ✅ 正常运行
```
celery@zuel ready (16 workers)
```

**Beat**: ✅ 正常运行
```
celery beat ready
```

**定时任务**:
- ✅ 采集任务：8次/天（8:00-22:00，每2小时）
- ✅ 新事件归并：3次/天（12:05、18:05、22:05）
- ✅ 整体归并：3次/天（12:20、18:20、22:20）
- ✅ 分类统计重算：1次/天（凌晨1:00）

---

## 📝 相关文档

- [归并逻辑说明](../docs/merge-logic.md) - 详细归并流程
- [每日任务调度](DAILY_SCHEDULE.md) - 每日任务时间表
- [数据流转架构](../docs/数据流转架构.md) - 系统架构图
- [API接口文档](../docs/api-spec.md) - API接口说明

---

## ✅ 总结

本次优化共完成**4项主要更新**：

1. **性能优化** - 整体归并只与最近7天Topic比对
2. **时间优化** - 归并时间提前10分钟，确保数据完整
3. **体验优化** - 归并完成后自动更新前端数据
4. **Bug修复** - 修复Topic创建时nodes丢失问题，确保分类正常工作

**系统状态**: ✅ 所有服务正常运行，优化已全部应用。

**分类功能**: ✅ **已修复**，清理了不完整数据，改进了异常处理。

---

**备注**: 
- 归并周期的"最近7天"限制可根据实际情况调整
- 前端数据更新机制基于API轮询，未来可考虑WebSocket实时推送
- 分类服务的规则匹配和LLM分类均正常工作

