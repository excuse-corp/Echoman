# 全局归并性能优化方案

## 📊 当前性能问题分析

### 实测数据（2025-11-07 PM周期）
- **总数据**: 469 条（162 个归并组）
- **执行轮次**: 20 轮
- **总耗时**: ~30 分钟
- **平均每轮**: ~90秒
- **处理进度**: 247/469 (52.8%)，仍有 222 条待处理

### 性能瓶颈识别

#### 1. **批处理限制过小** ⭐⭐⭐⭐⭐
```python
MAX_BATCH_SIZE = 50  # 每次最多处理50个归并组
```
- **问题**: 162个归并组需要4轮才能全部处理
- **影响**: 需要多次手动触发
- **优先级**: 最高

#### 2. **LLM调用串行执行** ⭐⭐⭐⭐
- **当前**: 每个归并组逐个调用LLM判断
- **耗时**: 每次LLM调用约1-3秒
- **累计**: 50个组 × 2秒 = 100秒/轮

#### 3. **向量检索效率** ⭐⭐⭐
- **当前**: 每个source_item查询Top-10候选Topics
- **数据库查询**: 逐个查询embedding和计算相似度

#### 4. **摘要生成耗时** ⭐⭐
- **当前**: 每个新Topic都尝试生成摘要
- **耗时**: 每个摘要约5-7秒
- **并发问题**: 数据库session冲突

---

## 🚀 优化方案

### 方案一：提高批处理限制（立即可用）

**难度**: ⭐  
**效果**: ⭐⭐⭐⭐⭐  
**实施时间**: 1分钟

```python
# backend/app/services/global_merge.py
class GlobalMergeService:
    # 修改前
    MAX_BATCH_SIZE = 50
    
    # 修改后
    MAX_BATCH_SIZE = 200  # 提高到200，一次处理完大部分数据
```

**预期效果**:
- 162个归并组 → 1轮完成（vs 当前4轮）
- 总耗时: ~2-3分钟（vs 当前30分钟）
- **推荐优先实施** ✅

---

### 方案二：实现自动循环处理（推荐）

**难度**: ⭐⭐  
**效果**: ⭐⭐⭐⭐⭐  
**实施时间**: 10分钟

```python
# backend/app/services/global_merge.py

async def run_global_merge(self, period: str) -> Dict[str, Any]:
    """执行全局归并（自动循环直到完成）"""
    
    total_merge = 0
    total_new = 0
    round_num = 0
    max_rounds = 10  # 最多循环10轮
    
    while round_num < max_rounds:
        round_num += 1
        
        # 获取待归并数据
        pending_groups = await self._get_pending_merge_groups(period)
        
        if not pending_groups:
            print(f"✅ 所有数据已处理完成（共{round_num-1}轮）")
            break
        
        print(f"🔄 第{round_num}轮归并: {len(pending_groups)} 个归并组")
        
        # 批量处理（限制每轮最多处理MAX_BATCH_SIZE）
        batch = pending_groups[:self.MAX_BATCH_SIZE]
        result = await self._process_batch(period, batch)
        
        total_merge += result['merged_count']
        total_new += result['new_count']
        
        print(f"   本轮: merge={result['merged_count']}, new={result['new_count']}")
    
    return {
        "total_rounds": round_num,
        "total_merge": total_merge,
        "total_new": total_new
    }
```

**预期效果**:
- 自动循环直到所有数据处理完成
- 无需手动触发多次
- **强烈推荐实施** ✅

---

### 方案三：LLM批量判断优化

**难度**: ⭐⭐⭐  
**效果**: ⭐⭐⭐⭐  
**实施时间**: 30分钟

#### 3.1 并行LLM调用

```python
# backend/app/services/global_merge.py

async def _batch_llm_judgement(
    self, 
    merge_groups: List[Dict],
    concurrent_limit: int = 5
) -> List[Dict]:
    """
    并行LLM判断
    
    Args:
        merge_groups: 归并组列表
        concurrent_limit: 并发限制（避免过载）
    """
    semaphore = asyncio.Semaphore(concurrent_limit)
    
    async def judge_with_limit(group):
        async with semaphore:
            return await self._llm_judge_single_group(group)
    
    # 并行执行
    tasks = [judge_with_limit(group) for group in merge_groups]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    return results
```

**预期效果**:
- 50个组 × 2秒 / 5并发 = 20秒（vs 当前100秒）
- **耗时减少80%** ✅

#### 3.2 LLM批量判断（高级）

```python
async def _batch_llm_judgement_bulk(
    self,
    merge_groups: List[Dict],
    batch_size: int = 10
) -> List[Dict]:
    """
    LLM批量判断（一次prompt处理多个组）
    
    注意: 需要调整prompt格式
    """
    prompt = self._build_bulk_judgement_prompt(merge_groups[:batch_size])
    response = await self.llm_provider.chat(prompt)
    return self._parse_bulk_response(response)
```

**预期效果**:
- 50个组 / 10批 = 5次LLM调用
- **耗时减少90%** 🚀

---

### 方案四：向量检索优化

**难度**: ⭐⭐⭐  
**效果**: ⭐⭐⭐  
**实施时间**: 20分钟

#### 4.1 批量向量检索

```python
# backend/app/services/global_merge.py

async def _batch_vector_search(
    self,
    source_items: List[SourceItem],
    top_k: int = 10
) -> Dict[int, List[Topic]]:
    """
    批量向量检索
    
    Returns:
        {source_item_id: [candidate_topics]}
    """
    # 1. 批量获取所有source_item的embedding
    embeddings = await self._batch_get_embeddings([item.id for item in source_items])
    
    # 2. 使用Chroma批量搜索（如果可用）
    if self.vector_service.db_type == "chroma":
        results = self.vector_service.collection.query(
            query_embeddings=embeddings,
            n_results=top_k
        )
        return self._parse_batch_results(results)
    
    # 3. 否则批量PostgreSQL查询
    return await self._batch_pg_vector_search(embeddings, top_k)
```

**预期效果**:
- 减少数据库往返次数
- **耗时减少50%**

#### 4.2 使用向量索引

```sql
-- 为embeddings表创建ivfflat索引（pgvector）
CREATE INDEX IF NOT EXISTS idx_embeddings_vector 
ON embeddings USING ivfflat (vector vector_cosine_ops)
WITH (lists = 100);
```

**预期效果**:
- 向量搜索速度提升10-100倍
- **大数据量下效果显著** 🚀

---

### 方案五：延迟摘要生成（推荐）

**难度**: ⭐⭐  
**效果**: ⭐⭐⭐  
**实施时间**: 10分钟

```python
# backend/app/services/global_merge.py

async def run_global_merge(self, period: str) -> Dict[str, Any]:
    """执行全局归并"""
    
    # ... 归并逻辑 ...
    
    # ❌ 不要在归并时生成摘要
    # await self._generate_summaries(new_topics)
    
    # ✅ 只创建占位摘要，异步生成
    for topic in new_topics:
        await self._create_placeholder_summary(topic)
    
    # ✅ 使用Celery异步任务生成摘要
    from app.tasks.summary_tasks import generate_topic_summaries
    generate_topic_summaries.delay([t.id for t in new_topics])
    
    return result
```

**预期效果**:
- 归并耗时减少30-50秒/轮
- 摘要在后台异步生成
- **用户体验更好** ✅

---

## 📋 实施优先级

### 🏃 立即实施（5分钟内）

1. **提高 MAX_BATCH_SIZE 到 200** ⭐⭐⭐⭐⭐
   ```python
   MAX_BATCH_SIZE = 200
   ```

### 🚶 短期实施（1小时内）

2. **实现自动循环处理** ⭐⭐⭐⭐⭐
3. **延迟摘要生成** ⭐⭐⭐⭐

### 🏗️ 中期优化（1-2天）

4. **LLM并行调用** ⭐⭐⭐⭐
5. **批量向量检索** ⭐⭐⭐
6. **添加向量索引** ⭐⭐⭐

### 🔬 长期优化（1周+）

7. **LLM批量判断** ⭐⭐⭐⭐⭐（需要prompt重构）
8. **缓存热门Topic embedding** ⭐⭐
9. **分布式处理** ⭐⭐⭐（大规模场景）

---

## 💡 快速实施脚本

### 立即优化（推荐）

```bash
cd /root/ren/Echoman/backend

# 1. 修改批处理限制
sed -i 's/MAX_BATCH_SIZE = 50/MAX_BATCH_SIZE = 200/' app/services/global_merge.py

# 2. 重启服务
killall -9 celery
nohup celery -A app.tasks.celery_app worker --loglevel=info > /dev/null 2>&1 &
nohup celery -A app.tasks.celery_app beat --loglevel=info > /dev/null 2>&1 &

echo "✅ 批处理限制已提高到200"
```

### 验证优化效果

```bash
# 测试归并性能
time python scripts/manual_trigger_global_merge.py 2025-11-07_PM

# 应该在2-3分钟内完成（vs 之前30分钟）
```

---

## 📈 预期优化效果

| 优化项 | 当前 | 优化后 | 提升 |
|--------|------|--------|------|
| **批处理大小** | 50组 | 200组 | 4x |
| **单轮耗时** | ~90秒 | ~40秒 | 2.25x |
| **总轮次** | 4轮+ | 1轮 | 4x |
| **总耗时** | 30分钟 | **2-3分钟** | **10-15x** 🚀 |

### 综合优化后
- **立即优化**: 耗时减少到 **2-3分钟** ✅
- **加上并行LLM**: 耗时减少到 **1-2分钟** 🚀
- **加上向量索引**: 耗时减少到 **< 1分钟** 🎯

---

## ⚠️ 注意事项

1. **LLM并发限制**: 避免超过API rate limit
2. **数据库连接池**: 增加 `pool_size` 配置
3. **内存使用**: 批处理增大会增加内存占用
4. **错误处理**: 添加重试机制和错误日志

---

**建议**: 先实施方案一和方案二，可立即看到10x+的性能提升！

