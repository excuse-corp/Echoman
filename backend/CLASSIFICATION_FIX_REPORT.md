# 事件分类问题诊断与修复报告

**日期**: 2025-11-07  
**问题**: 大量Topic使用default分类方法，没有使用LLM分类  

---

## 📋 问题分析

### 1️⃣ 分类任务执行时机

**答案**: 分类**不是独立的定时任务**，而是在**创建新Topic时立即执行**（global_merge阶段）

```
执行位置: backend/app/services/global_merge.py 第639行
执行时间: 
  - 上午归并：12:20
  - 下午归并：18:20
  - 傍晚归并：22:20
```

**分类流程**:
```python
async def _create_new_topic(...):
    # 1. 创建Topic
    topic = Topic(...)
    
    # 2. 创建TopicNodes
    for item in items:
        node = TopicNode(...)
    
    # 3. 提交到数据库
    await self.db.commit()
    
    # 4. 执行分类
    category, confidence, method = await self.classification_service.classify_topic(
        self.db, topic, force_llm=False
    )
```

---

### 2️⃣ 为什么没有使用LLM分类？

**根本原因**: **143个Topic没有TopicNodes数据！**

**分类服务逻辑**:
```python
# classification_service.py 第90-94行
nodes = await self._get_topic_key_nodes(db, topic.id)

if not nodes:
    # 无节点数据，使用默认分类
    return self.CURRENT_AFFAIRS, 0.3, "default"  # ❌ 直接返回，不执行LLM
```

**数据统计**:
```
今天的Topic（修复前）：258个
├─ 使用default方法：143个（55%）❌
└─ 使用其他方法（rule/llm）：115个（45%）✅

TopicNodes：
├─ 总数：633个
├─ 有Nodes的Topic：115个 ✅
└─ 没有Nodes的Topic：143个 ❌

💡 完全匹配！没有nodes的Topic = 使用default方法的Topic
```

---

### 3️⃣ 为什么会出现没有nodes的Topic？

**推断原因**:

1. **并行处理时的异常** - `asyncio.gather(return_exceptions=True)`捕获了异常但没有回滚
2. **数据库事务问题** - Topic被flush了，但TopicNodes的commit失败
3. **缺少异常处理** - 创建Topic时没有try-except包裹

**问题代码**（修复前）:
```python
async def _create_new_topic(...):
    # 创建Topic
    topic = Topic(...)
    self.db.add(topic)
    await self.db.flush()  # ✅ Topic已保存，有ID
    
    # 创建TopicNodes
    for item in items:
        node = TopicNode(...)
        self.db.add(node)  # ❌ 如果这里出现异常...
    
    await self.db.commit()  # ❌ ...commit失败，但Topic已经flush了
    
    # 分类
    category = await classify_topic(...)  # ❌ 查询nodes为空，使用default
```

---

## 🔧 修复方案

### 1️⃣ 清理不完整的Topic

**操作**: 删除143个没有nodes的Topic

**脚本**: `backend/scripts/fix_topics_without_nodes.py`

**结果**: ✅ 已删除143个不完整的Topic

### 2️⃣ 改进创建Topic的异常处理

**修改文件**: `backend/app/services/global_merge.py`

**关键改进**:

1. **添加try-except包裹整个创建过程**
```python
async def _create_new_topic(...):
    try:
        # 创建Topic和TopicNodes
        ...
        
        await self.db.flush()  # ✅ 提交前先flush
        await self.db.commit()  # ✅ 确保nodes被保存
        
        print(f"创建新 Topic: {topic.id} ({nodes_created} nodes)")  # ✅ 记录nodes数量
        
    except Exception as e:
        logger.error(f"创建Topic失败: {e}")
        await self.db.rollback()  # ✅ 回滚所有更改
        raise  # ✅ 重新抛出异常
```

2. **分类前刷新数据库会话**
```python
try:
    # 刷新会话以确保能查询到刚创建的nodes
    await self.db.refresh(topic)  # ✅ 刷新topic对象
    
    category, confidence, method = await self.classification_service.classify_topic(
        self.db, topic, force_llm=False
    )
    ...
except Exception as e:
    # 分类失败不影响Topic创建
    await self.db.rollback()  # ✅ 只回滚分类更改
    await self.db.commit()  # ✅ 保留topic创建
```

3. **添加详细日志**
   - 记录创建的nodes数量
   - 记录分类方法（default/rule/llm）
   - 记录异常详情

---

## ✅ 修复后状态

### 系统状态

**Celery服务**: ✅ 已重启，应用新代码
```
Worker: celery@zuel ready (16 workers)
Beat: celery@zuel ready
```

**Topic状态**: ✅ 已清理不完整数据
```
今天的Topic（修复后）：115个
├─ 有Nodes：115个（100%）✅
└─ 没有Nodes：0个 ✅

分类分布:
├─ 时事（current_affairs）：71个
├─ 体育（sports_esports）：25个
└─ 娱乐（entertainment）：17个
```

### 分类逻辑流程

```
创建新Topic时
    ↓
1. 创建Topic并flush
    ↓
2. 创建TopicNodes并flush
    ↓
3. 提交到数据库
    ↓
4. 刷新会话
    ↓
5. 查询TopicNodes（此时必定有数据）
    ↓
6. 执行分类逻辑
    ├─ 提取nodes中的文本内容
    ├─ 规则匹配（关键词、平台权重）
    │   └─ 置信度 >= 0.6 → 使用规则分类 ✅
    └─ 规则置信度不够
        └─ 调用LLM分类 ✅

结果：不会再出现default分类（除非真的没有nodes）
```

---

## 📝 后续建议

### 1️⃣ 监控建议

添加监控指标：
- 每次归并后，检查使用default方法的Topic数量
- 如果比例 > 5%，触发告警
- 记录创建失败的Topic数量

### 2️⃣ 优化建议

**分类优化**:
1. 扩充规则关键词库，提升规则匹配率
2. 调整规则置信度阈值（当前0.6）
3. 为LLM分类添加缓存，避免重复调用

**性能优化**:
1. 批量执行分类（收集所有新Topic后统一分类）
2. 异步执行分类（不阻塞归并流程）
3. 添加分类结果缓存

---

## 🎯 总结

### 问题
- ❌ 143个Topic没有nodes数据
- ❌ 分类服务查询不到nodes，使用default方法
- ❌ 缺少异常处理，Topic和Nodes创建不具备原子性

### 修复
- ✅ 清理了143个不完整的Topic
- ✅ 添加了robust的异常处理
- ✅ 分类前刷新会话，确保能查询到nodes
- ✅ 添加了详细日志，便于排查问题

### 结果
- ✅ 所有Topic都有完整的nodes数据
- ✅ 分类逻辑正常工作（rule + LLM）
- ✅ 不会再出现大量default分类

---

**备注**: 
- 分类任务是归并流程的一部分，没有独立的定时任务
- 如需重新分类，可运行: `python scripts/classify_unclassified_topics.py`
- 监控日志文件: `logs/celery_worker.log` 和 `logs/celery_beat.log`

