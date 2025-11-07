# 整体归并性能优化方案

**当前问题**: 处理46组事件耗时33分钟（1998秒），平均每组43.4秒  
**目标**: 将耗时降低到5-10分钟以内

---

## 📊 性能瓶颈分析

### 当前执行流程

```
for 每个group (串行，46组):
    1. 向量检索候选Topics        (~1-2秒，数据库查询)
    2. LLM关联判定               (~5秒，LLM API调用)
    3. 如果决策为"new":
       a. 创建新Topic            (~0.5秒，数据库)
       b. LLM分类                (~5秒，LLM API调用)
       c. LLM生成摘要            (~10秒，LLM API调用)
    4. 如果决策为"merge":
       a. 更新Topic              (~0.5秒，数据库)
       b. LLM增量摘要更新        (~5秒，LLM API调用)
    
平均耗时: ~20-25秒/组 (new) 或 ~10-15秒/组 (merge)
实际测量: 43.4秒/组 (包含异常处理、日志等开销)
```

### 瓶颈识别

1. **串行处理** ⭐⭐⭐⭐⭐ (最严重)
   - 46个group完全串行
   - 无法利用并发能力

2. **LLM调用次数多** ⭐⭐⭐⭐
   - 每个group至少1次（判定）
   - new: 额外2次（分类+摘要）
   - merge: 额外0-1次（增量摘要）
   - 总计: 46次判定 + ~30次分类 + ~30次摘要 = ~106次LLM调用

3. **阻塞式摘要生成** ⭐⭐⭐
   - 摘要生成阻塞主流程
   - 实际上可以异步处理

4. **数据库查询优化空间** ⭐⭐
   - 向量检索涉及多次JOIN
   - 可以批量查询

---

## 🚀 优化方案

### 方案1: 并行处理 (立即实施) ⭐⭐⭐⭐⭐

**目标**: 将耗时从33分钟降低到5-7分钟

**实现**:
```python
# 当前: 串行处理
for group in merge_groups:
    decision = await self._process_event_group(group, halfday_period)

# 优化后: 批量并行处理
CONCURRENT_BATCH_SIZE = 10  # 每批并行处理10个

for i in range(0, len(merge_groups), CONCURRENT_BATCH_SIZE):
    batch = merge_groups[i:i + CONCURRENT_BATCH_SIZE]
    results = await asyncio.gather(
        *[self._process_event_group(group, halfday_period) for group in batch],
        return_exceptions=True
    )
    # 处理结果...
```

**预期效果**:
- 10个并发: 1998秒 / 10 ≈ 200秒 (3.3分钟)
- 加上批次切换开销: **~5分钟**
- **速度提升: 6-7倍**

**风险**:
- LLM API限流（需要控制并发数）
- 数据库连接池压力（需要调整pool_size）
- 内存占用增加

**缓解措施**:
- 控制并发数为5-10
- 增加数据库连接池大小（已配置pool_size=10）
- 添加异常处理，失败的group重试

---

### 方案2: 异步摘要生成 (立即实施) ⭐⭐⭐⭐

**目标**: 摘要生成不阻塞主流程

**实现**:
```python
# 当前: 同步生成摘要
async def _create_new_topic(...):
    topic = Topic(...)
    self.db.add(topic)
    await self.db.commit()
    
    # 阻塞主流程
    summary = await self.summary_service.generate_full_summary(self.db, topic)
    await self.db.commit()

# 优化后: 收集待生成摘要的topic，批量异步处理
async def _create_new_topic(...):
    topic = Topic(...)
    self.db.add(topic)
    await self.db.commit()
    return topic  # 立即返回，不等待摘要

# 在主流程最后批量生成摘要
async def run_global_merge(...):
    # ... 处理所有groups ...
    
    # 批量异步生成摘要
    await self._batch_generate_summaries(new_topics)
```

**预期效果**:
- 每个new topic节省10秒（摘要生成时间）
- 假设23个new topics: 节省230秒 (3.8分钟)
- 与方案1结合: **总耗时降至 1-2分钟**

---

### 方案3: 批量LLM调用 (中期优化) ⭐⭐⭐

**目标**: 将多个判定合并为一个batch请求

**实现**:
```python
# 当前: 每个group单独调用LLM
async def _llm_judge_relation(item, candidates):
    prompt = f"判断新事件是否为已有主题的新进展: {item.title}..."
    response = await self.llm_provider.chat_completion([{"role": "user", "content": prompt}])

# 优化后: 批量判定
async def _batch_llm_judge(batch_items_and_candidates):
    prompt = """判断以下多个新事件是否为对应候选主题的新进展:
    
事件1: ...
候选主题: ...

事件2: ...
候选主题: ...
...
"""
    response = await self.llm_provider.chat_completion([{"role": "user", "content": prompt}])
```

**预期效果**:
- 减少API调用开销（网络延迟）
- 每批5-10个: 节省~50%时间
- **配合方案1+2: 总耗时可降至 1分钟以内**

**挑战**:
- Prompt变长，Token消耗增加
- 需要更复杂的响应解析
- 需要LLM支持长上下文

---

### 方案4: 两阶段处理 (中期优化) ⭐⭐⭐

**目标**: 快速决策（merge/new），延迟详细处理

**实现**:
```python
# 阶段1: 快速决策（5分钟）
for group in merge_groups (并行):
    决策 = 向量检索 + LLM判定
    if 决策 == "new":
        创建Topic（不生成摘要）
    else:
        归并到Topic（不更新摘要）

# 阶段2: 后台处理（不阻塞用户）
Celery异步任务:
    批量生成摘要
    批量分类
    更新增量摘要
```

**预期效果**:
- 用户快速看到新数据（5分钟内）
- 摘要等详细信息逐步完善
- **用户体验大幅提升**

---

### 方案5: 数据库查询优化 (小幅优化) ⭐⭐

**实现**:
1. 预加载候选Topics的相关数据（减少JOIN）
2. 批量查询SourceItem和Embedding
3. 使用数据库索引优化向量检索

**预期效果**:
- 每个group节省0.5-1秒
- 总计节省~30-60秒

---

## 📝 实施计划

### 阶段一：立即实施（本周）

1. **并行处理** (方案1)
   - 修改 `run_global_merge` 主循环
   - 添加 `CONCURRENT_BATCH_SIZE = 10`
   - 使用 `asyncio.gather` 批量处理
   - **预期效果: 33分钟 → 5分钟**

2. **异步摘要生成** (方案2)
   - 修改 `_create_new_topic`，分离摘要生成
   - 添加 `_batch_generate_summaries` 方法
   - **预期效果: 5分钟 → 2分钟**

### 阶段二：中期优化（下周）

3. **批量LLM调用** (方案3)
   - 实现批量判定逻辑
   - 调整Prompt格式
   - **预期效果: 2分钟 → 1分钟**

4. **两阶段处理** (方案4)
   - 拆分为快速决策 + 后台处理
   - 添加Celery异步任务
   - **预期效果: 用户等待时间 < 5分钟**

### 阶段三：长期优化

5. **数据库优化** (方案5)
6. **缓存策略** (Redis缓存向量检索结果)
7. **智能跳过** (已处理过的相似事件直接跳过)

---

## 🎯 预期性能提升

| 优化方案 | 当前耗时 | 优化后 | 提升比例 | 实施难度 |
|---------|---------|--------|---------|---------|
| **无优化** | 33分钟 | - | - | - |
| 方案1: 并行处理 | 33分钟 | **5分钟** | **6.6倍** | ⭐⭐ 简单 |
| +方案2: 异步摘要 | 5分钟 | **2分钟** | **16.5倍** | ⭐⭐ 简单 |
| +方案3: 批量LLM | 2分钟 | **1分钟** | **33倍** | ⭐⭐⭐ 中等 |
| +方案4: 两阶段处理 | 1分钟 | **用户等待<5分钟** | **体验极佳** | ⭐⭐⭐⭐ 复杂 |

---

## ⚠️ 注意事项

### LLM API限流

- **问题**: 并发调用可能触发限流
- **解决**: 
  - 控制并发数（5-10）
  - 添加重试逻辑
  - 监控API响应时间

### 数据库连接池

- **问题**: 并发增加导致连接池耗尽
- **解决**: 
  - 已配置 `pool_size=10, max_overflow=20`
  - 足够支持10个并发任务
  - 监控连接池使用率

### 内存占用

- **问题**: 并行处理增加内存占用
- **解决**: 
  - 分批处理（每批10个）
  - 及时释放资源
  - 监控内存使用

### 异常处理

- **问题**: 并行处理中单个失败可能影响整批
- **解决**: 
  - `asyncio.gather(return_exceptions=True)`
  - 单独处理每个group的异常
  - 记录失败的group，后续重试

---

## 📈 监控指标

添加详细的性能监控：

```python
import time

# 记录各阶段耗时
metrics = {
    "vector_search_time": [],
    "llm_judge_time": [],
    "create_topic_time": [],
    "classification_time": [],
    "summary_time": [],
}

# 在每个关键步骤记录时间
start = time.time()
candidates = await self._retrieve_candidate_topics(representative)
metrics["vector_search_time"].append(time.time() - start)

# 输出统计
print(f"""
性能统计:
- 向量检索平均: {np.mean(metrics['vector_search_time']):.2f}s
- LLM判定平均: {np.mean(metrics['llm_judge_time']):.2f}s
- 创建Topic平均: {np.mean(metrics['create_topic_time']):.2f}s
- 分类平均: {np.mean(metrics['classification_time']):.2f}s
- 摘要生成平均: {np.mean(metrics['summary_time']):.2f}s
""")
```

---

## 🔧 实施优先级

1. **⭐⭐⭐⭐⭐ 高优先级**: 方案1（并行处理） + 方案2（异步摘要）
   - 效果最明显（33分钟 → 2分钟）
   - 实施简单，风险低
   - **建议立即实施**

2. **⭐⭐⭐ 中优先级**: 方案3（批量LLM调用）
   - 进一步优化（2分钟 → 1分钟）
   - 需要调整Prompt和解析逻辑
   - **建议下周实施**

3. **⭐⭐ 低优先级**: 方案4（两阶段处理）+ 方案5（数据库优化）
   - 收益递减
   - 实施复杂度较高
   - **长期优化**

---

**下一步**: 实施方案1和方案2，预计将归并耗时降至2分钟以内！

