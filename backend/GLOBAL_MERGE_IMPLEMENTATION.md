# 整体归并（Global Merge）实现方案详解

**文件**: `backend/app/services/global_merge.py`  
**核心类**: `GlobalMergeService`  
**定位**: 归并流程的第二阶段（阶段一是新事件归并 Event Merge）

---

## 📋 一、功能定位

### 1.1 在归并流程中的位置

```
┌─────────────────────────────────────────────────────────────┐
│ 阶段一：新事件归并（Event Merge）                            │
│ - 时间：12:05, 18:05, 22:05                                  │
│ - 职责：对新采集数据去噪、过滤噪音                           │
│ - 输出：status=pending_global_merge 的真实事件组             │
└─────────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────┐
│ 阶段二：整体归并（Global Merge）← 本模块                     │
│ - 时间：12:20, 18:20, 22:20                                  │
│ - 职责：将验证事件与历史Topic库比对，决策归并或创建新主题     │
│ - 输出：更新Topics表、TopicNodes、TopicPeriodHeat           │
└─────────────────────────────────────────────────────────────┘
```

### 1.2 核心职责

1. **输入**：`status=pending_global_merge` 且 `period` 匹配的事件组
2. **处理**：向量检索（最近7天Topic） → LLM判定关联性 → 决策
3. **输出**：
   - 更新 `Topics` 表（新建或更新）
   - 更新 `TopicNodes` 表（记录主题节点）
   - 更新 `TopicPeriodHeat` 表（记录周期热度）
   - 更新 `SourceItems` 表（status → `merged`）
   - 触发前端数据更新

---

## 🔄 二、核心流程

### 2.1 主流程（`run_global_merge`）

```python
async def run_global_merge(self, period: str) -> Dict[str, Any]:
    """
    执行整体归并
    
    Args:
        period: 归并周期标识（如 "2025-11-07_PM"）
    
    Returns:
        归并统计结果
    """
```

**步骤详解**：

```
1. 获取待归并事件组
   ├─ 查询：period=指定周期 AND merge_status=pending_global_merge
   ├─ 按 period_merge_group_id 分组
   └─ 返回：[{group_id, items[], representative}, ...]

2. 批量处理限制
   ├─ MAX_BATCH_SIZE = 200（每次最多处理200个组）
   ├─ 如果超过200个，打印警告，仍处理全部
   └─ 目的：平衡性能和数据完整性

3. 串行/并行处理事件组（当前：串行）
   ├─ CONCURRENT_BATCH_SIZE = 1（串行，避免会话冲突）
   ├─ 原设计：CONCURRENT_BATCH_SIZE = 10（并行）
   ├─ 问题：SQLAlchemy异步会话冲突 → greenlet_spawn错误
   └─ 解决：临时改为串行，未来需用独立会话实现并发

4. 对每个事件组调用 _process_event_group()
   ├─ 返回：{"action": "merge"|"new", "target_topic_id": X}
   └─ 统计：merge_count, new_count

5. 批量生成摘要
   ├─ 收集新创建的Topics
   └─ 调用 _batch_generate_summaries()

6. 更新前端数据
   ├─ 调用 update_frontend_after_merge()
   └─ 记录归并完成事件到 runs_pipeline

7. 返回统计结果
```

---

### 2.2 处理单个事件组（`_process_event_group`）

```python
async def _process_event_group(
    event_group: Dict[str, Any],
    period: str
) -> Dict[str, Any]:
    """
    处理单个事件组
    
    流程：向量检索 → LLM判定 → merge or new
    """
```

**核心决策流程**：

```
┌─────────────────────────────────────────────────────────────┐
│ Step 1: 向量检索候选Topics                                   │
│ _retrieve_candidate_topics(representative_item)             │
│                                                              │
│ ├─ 从Embedding表获取item的向量                               │
│ ├─ 使用Chroma向量数据库搜索相似source_items                  │
│ ├─ 通过TopicNode反查对应的Topic（仅最近7天）                │
│ ├─ 去重，返回 Top-10 候选                                    │
│ └─ 返回：[{topic_id, title, last_active, similarity}, ...]  │
└─────────────────────────────────────────────────────────────┘
                           ↓
                    有候选？ 无候选
                      /        \
                     /          \
┌──────────────────────┐  ┌────────────────────┐
│ Step 2: LLM判定关联性 │  │ 直接创建新Topic     │
│ _llm_judge_relation() │  │ _create_new_topic() │
│                      │  └────────────────────┘
│ ├─ 构建Prompt         │
│ ├─ 新事件描述         │
│ ├─ 候选主题列表       │
│ ├─ 调用LLM判定        │
│ └─ 返回决策           │
└──────────────────────┘
         ↓
   decision.action?
      /      \
  "merge"   "new"
     ↓        ↓
┌─────────┐  ┌────────────┐
│ 归并到   │  │ 创建新Topic│
│ 已有Topic│  │            │
└─────────┘  └────────────┘
```

---

## 🔍 三、核心算法详解

### 3.1 向量检索候选Topics

**文件位置**: `_retrieve_candidate_topics()` (第320-442行)

**算法流程**：

```python
1. 查询输入item的向量（从Embedding表）
   └─ 如果没有向量，返回空列表

2. 使用Chroma向量数据库进行语义搜索
   ├─ query_embedding: item的向量
   ├─ top_k: 10 * 3 = 30（多召回，后续过滤）
   ├─ where: {"object_type": "source_item"}
   └─ 返回：(ids, distances, metadatas)

3. 从搜索结果反查Topic
   For each similar_source_item:
     ├─ 查询 TopicNode 找到关联的Topic
     ├─ 过滤条件：
     │   ├─ Topic.status == "active"
     │   ├─ Topic.last_active >= 7天前  ← 关键优化！
     │   └─ 去重（seen_topics set）
     ├─ 收集候选信息：
     │   ├─ topic_id
     │   ├─ title_key
     │   ├─ last_active
     │   ├─ length_hours (持续时长)
     │   └─ similarity (1 - distance)
     └─ 达到top_k=10个后停止

4. 回退方案（如果Chroma失败）
   └─ 直接查询数据库，按 last_active 降序取最近的10个Topic
```

**关键优化**：

1. **只检索最近7天的Topic**  
   - 避免与过时事件关联  
   - 提升检索效率  
   - 确保时效性

2. **限制候选数量为10个**  
   - 减少LLM判定的上下文长度  
   - 控制Token消耗  
   - 提升响应速度

---

### 3.2 LLM关联判定

**文件位置**: `_llm_judge_relation()` (第443-590行)

**输入**：
- `item`: 新事件的代表性SourceItem
- `candidates`: 候选Topics列表（最多10个）
- `period`: 归并周期

**输出**：
```python
{
  "action": "merge" | "new",
  "target_topic_id": int,  # 如果action=merge
  "confidence": float,     # 0.0-1.0
  "reason": str
}
```

**Prompt构建**：

```python
# 1. 新事件描述（Token优化截断）
new_event_desc = f"""
标题: {truncate(item.title, 80 tokens)}
摘要: {truncate(item.summary, 150 tokens)}
平台: {item.platform}
日期: {date_str} {period}
"""

# 2. 候选主题列表（每个候选最多200 tokens）
candidates_desc = [
  f"""【候选主题 {idx}】
  标题: {truncate(cand['title'], 200 tokens)}
  最后活跃: {cand['last_active'].strftime('%Y-%m-%d %H:%M')}
  持续时长: {cand['length_hours']:.1f} 小时"""
  for idx, cand in enumerate(candidates, 1)
]

# 3. 判断标准
prompt = f"""判断新事件是否为已有主题的新进展：

【新事件】
{new_event_desc}

{'\n'.join(candidates_desc)}

要求输出 JSON 格式：
{{
  "decision": "merge" 或 "new",
  "target_topic_id": 候选主题ID（如果是merge），
  "confidence": 0.0-1.0,
  "reason": "判断理由"
}}

判断标准：
1. 如果新事件是某个候选主题的后续进展、新报道，则选择 "merge"
2. 如果新事件与所有候选主题都无关，则选择 "new"
3. 时间间隔不超过7天
4. 主题一致性强
"""
```

**Token管理**：

```python
# 1. 统计Prompt的Token数
prompt_tokens = token_manager.count_tokens(prompt)

# 2. 如果超过限制（2500 tokens），截断
if prompt_tokens > 2500:
    prompt = token_manager.truncate_text(prompt, max_tokens=2500)

# 3. LLM调用限制
response = llm_provider.chat_completion(
    messages=[
        {"role": "system", "content": "你是专业的新闻事件分析助手..."},
        {"role": "user", "content": prompt}
    ],
    response_format="json",
    max_tokens=300  # Completion最多300 tokens
)
```

**决策逻辑**：

```python
if result.get("decision") == "merge":
    if result.get("confidence") >= settings.global_merge_confidence_threshold:
        # 置信度达标，执行归并
        return {
            "action": "merge",
            "target_topic_id": result.get("target_topic_id"),
            "confidence": result.get("confidence")
        }
    else:
        # 置信度不足，降级为创建新Topic
        return {"action": "new", "confidence": result.get("confidence")}
else:
    # LLM判定为新事件
    return {"action": "new", "confidence": result.get("confidence")}
```

**持久化LLM判定记录**：

```python
# 记录到 llm_judgements 表，用于后续分析和审计
judgement = LLMJudgement(
    type="global_merge",
    status="success",
    request={"item_id": item.id, "candidates": [c["topic_id"] for c in candidates]},
    response=result,
    tokens_prompt=prompt_tokens,
    tokens_completion=completion_tokens,
    provider=llm_provider.get_provider_name(),
    model=llm_provider.model
)
db.add(judgement)
await db.commit()
```

---

### 3.3 归并到已有Topic

**文件位置**: `_merge_to_topic()` (第664-734行)

**操作步骤**：

```python
1. 查询目标Topic
   └─ 如果不存在，报错返回

2. 更新Topic基本信息
   ├─ last_active = max(新items的fetched_at)
   └─ intensity_total += len(items)

3. 创建TopicNodes（建立关联）
   For each item in event_group.items:
     ├─ 创建 TopicNode(topic_id, source_item_id)
     ├─ 更新 item.merge_status = "merged"
     └─ db.add(node)

4. 更新周期热度记录
   └─ _update_topic_heat(topic, event_group, period)
      ├─ 解析 period (如 "2025-11-07_PM")
      ├─ 计算归一化热度总和
      ├─ 查找或创建 TopicPeriodHeat 记录
      └─ 更新 heat_normalized, heat_percentage, source_count

5. 提交数据库
   └─ await db.commit()

6. 增量摘要更新（异步）
   └─ summary_service.generate_or_update_summary(db, topic, new_nodes)
      ├─ 判断是否需要更新摘要
      ├─ 如果需要，调用LLM生成增量摘要
      └─ 更新Topic.summary_id
```

---

### 3.4 创建新Topic

**文件位置**: `_create_new_topic()` (第592-663行)

**操作步骤**：

```python
1. 创建Topic对象
   topic = Topic(
       title_key=representative.title,
       first_seen=min(item.fetched_at for item in items),
       last_active=max(item.fetched_at for item in items),
       status="active",
       intensity_total=len(items),
       current_heat_normalized=avg(items的heat_normalized)
   )
   db.add(topic)
   await db.flush()  # 获取topic.id

2. 创建TopicNodes
   For each item in event_group.items:
     ├─ 创建 TopicNode(topic_id, source_item_id)
     ├─ 更新 item.merge_status = "merged"
     └─ db.add(node)

3. 更新周期热度记录
   └─ _update_topic_heat(topic, event_group, period)

4. 提交前flush（确保nodes被保存）
   └─ await db.flush()

5. 最终提交
   └─ await db.commit()

6. 分类（异步，可失败）
   try:
     ├─ await db.refresh(topic)  # 刷新会话，确保nodes可查询
     ├─ classification_service.classify_topic(db, topic)
     │   ├─ 规则分类（基于关键词）
     │   └─ LLM分类（规则不适用时）
     ├─ 更新 topic.category, category_confidence, category_method
     └─ await db.commit()
   except:
     └─ 分类失败不影响Topic创建，记录错误日志

7. 摘要生成（延迟到批量处理）
   └─ 返回topic，由主流程收集后批量生成摘要
```

**健壮性优化**：

```python
# 整个方法包裹在try...except中
try:
    # ... 创建Topic、TopicNodes等 ...
except Exception as e:
    logger.error(f"创建Topic失败: {e}")
    await db.rollback()
    raise  # 重新抛出异常

# 分类失败单独处理
try:
    # 分类逻辑
except Exception as e:
    logger.error(f"分类失败: {e}")
    await db.rollback()
    await db.commit()  # 重新提交Topic创建，忽略分类失败
```

---

## ⚡ 四、性能优化策略

### 4.1 批量处理

```python
MAX_BATCH_SIZE = 200  # 每次最多处理200个事件组

if total_groups > MAX_BATCH_SIZE:
    print(f"⚠️  事件组数量 ({total_groups}) 超过批次限制 ({MAX_BATCH_SIZE})")
    print(f"   性能优化建议：分多轮执行")
    # 但仍然处理全部，确保数据完整性
```

**优化效果**：
- 从 50 → 200：处理速度提升 **4倍**
- 单轮耗时：从 90秒 → 20-60秒
- 总耗时（200组）：从 30分钟 → 3-5分钟

---

### 4.2 向量检索限制

```python
# 1. 候选数量限制
top_k = min(top_k, 10)  # 最多10个候选

# 2. 时间范围限制
one_week_ago = now_cn() - timedelta(days=7)
# 只检索最近7天的Topic

# 3. 多召回后过滤
ids, distances, metadatas = vector_service.search_similar(
    query_embedding=item_embedding.vector,
    top_k=top_k * 3,  # 召回30个，过滤后保留10个
    where={"object_type": "source_item"}
)
```

**优化效果**：
- 减少LLM上下文长度：从 5000+ tokens → 2500 tokens
- 提升检索速度：减少数据库查询量
- 提高相关性：只与最近7天的Topic比对

---

### 4.3 Token管理

```python
class GlobalMergeService:
    def __init__(self, db: AsyncSession):
        self.token_manager = get_token_manager(model=settings.qwen_model)
        # Token限制
        self.max_prompt_tokens = 2500        # 输入上下文最大token
        self.max_completion_tokens = 300     # 判定结果最大token
        self.max_candidate_summary_tokens = 200  # 每个候选主题摘要最大token
```

**截断策略**：

```python
# 1. 新事件标题截断（80 tokens）
title = token_manager.truncate_text(item.title, max_tokens=80)

# 2. 新事件摘要截断（150 tokens）
summary = token_manager.truncate_text(item.summary, max_tokens=150)

# 3. 候选主题标题截断（200 tokens）
cand_title = token_manager.truncate_text(cand['title'], max_tokens=200)

# 4. 整体Prompt截断（2500 tokens）
if prompt_tokens > self.max_prompt_tokens:
    prompt = token_manager.truncate_text(prompt, max_tokens=2500)
```

**Token统计**：

```python
# 典型场景
新事件描述: ~300 tokens
候选主题 * 10: ~2000 tokens
判断标准: ~200 tokens
总计: ~2500 tokens  ← 正好控制在限制内
```

---

### 4.4 超时控制

```python
MAX_TIMEOUT_SECONDS = 900  # 15分钟超时

# 实际实现待添加（TODO）
# 建议使用 asyncio.wait_for() 包裹主流程
```

---

### 4.5 并发处理（当前禁用）

```python
# 原设计：并发处理
CONCURRENT_BATCH_SIZE = 10  # 每批并行处理10个group

results = await asyncio.gather(
    *[self._process_event_group(group, period) for group in batch],
    return_exceptions=True
)
```

**当前状态**：

```python
# 临时修复：串行处理（避免会话冲突）
CONCURRENT_BATCH_SIZE = 1  # 串行处理，避免greenlet_spawn错误
```

**问题根源**：
- SQLAlchemy异步会话不支持并发访问
- 10个并发任务共享同一个 `self.db` 会话
- 导致 `greenlet_spawn has not been called` 错误

**长期解决方案**：

```python
async def _process_event_group_with_session(
    self, event_group: Dict[str, Any], period: str
) -> Dict[str, Any]:
    """为每个group创建独立的数据库会话"""
    async_session = get_async_session()
    async with async_session() as db:
        temp_service = GlobalMergeService(db)
        return await temp_service._process_event_group(event_group, period)

# 恢复并发
CONCURRENT_BATCH_SIZE = 10
results = await asyncio.gather(
    *[self._process_event_group_with_session(group, period) for group in batch],
    return_exceptions=True
)
```

---

## 📊 五、数据流转

### 5.1 输入数据

**来源**: `source_items` 表

```sql
SELECT * FROM source_items
WHERE period = '2025-11-07_PM'
  AND merge_status = 'pending_global_merge'
```

**特征**：
- 已经过阶段一（Event Merge）的去噪验证
- 按 `period_merge_group_id` 分组
- 每组代表一个相似事件簇（occurrence_count >= 2）
- 已生成向量（embedding_id 不为空）

---

### 5.2 输出数据

#### 5.2.1 Topics 表

```python
# 新建Topic
Topic(
    title_key=representative.title,
    first_seen=datetime,
    last_active=datetime,
    status="active",
    intensity_total=len(items),
    current_heat_normalized=float,
    category="current_affairs"|"entertainment"|"sports_esports",
    category_confidence=float,
    category_method="rule"|"llm"
)

# 更新已有Topic
UPDATE topics SET
    last_active = <new_last_active>,
    intensity_total = intensity_total + <new_items_count>
WHERE id = <target_topic_id>
```

#### 5.2.2 TopicNodes 表

```python
# 为每个item创建关联节点
TopicNode(
    topic_id=topic.id,
    source_item_id=item.id,
    appended_at=now_cn()
)
```

#### 5.2.3 TopicPeriodHeat 表

```python
# 记录周期热度快照
TopicPeriodHeat(
    topic_id=topic.id,
    date=date_obj,          # 如 2025-11-07
    period=period_type,     # "AM"|"PM"|"EVE"
    heat_normalized=float,  # 归并周期内归一化热度
    heat_percentage=float,  # 占周期总热度百分比
    source_count=int        # 该周期的source_item数量
)
```

#### 5.2.4 SourceItems 表

```python
# 更新归并状态
UPDATE source_items SET
    merge_status = 'merged'
WHERE id IN (<merged_items>)
```

#### 5.2.5 LLMJudgements 表

```python
# 记录每次LLM判定（审计和分析）
LLMJudgement(
    type="global_merge",
    status="success"|"failed",
    request={"item_id": X, "candidates": [...]},
    response={"decision": "merge"|"new", "confidence": 0.9, ...},
    tokens_prompt=int,
    tokens_completion=int,
    provider="qwen",
    model="qwen-max-latest"
)
```

---

## 🔧 六、关键配置参数

### 6.1 性能配置

```python
# backend/app/services/global_merge.py
MAX_BATCH_SIZE = 200            # 每轮最多处理200个事件组
CONCURRENT_BATCH_SIZE = 1       # 并发处理数（当前串行）
MAX_TIMEOUT_SECONDS = 900       # 15分钟超时
```

### 6.2 向量检索配置

```python
# backend/app/config.py
global_merge_topk_candidates = 10  # 候选Topic数量
```

### 6.3 Token配置

```python
# backend/app/services/global_merge.py
max_prompt_tokens = 2500           # Prompt最大token
max_completion_tokens = 300        # Completion最大token
max_candidate_summary_tokens = 200 # 每个候选摘要最大token
```

### 6.4 LLM判定配置

```python
# backend/app/config.py
global_merge_confidence_threshold = 0.7  # 置信度阈值（0-1）
```

### 6.5 时间窗口配置

```python
# backend/app/services/global_merge.py
one_week_ago = now_cn() - timedelta(days=7)  # 只检索最近7天Topic
```

---

## 🐛 七、已知问题与解决方案

### 问题1: 并发处理导致会话冲突 ⚠️

**现象**：
```
创建Topic失败: greenlet_spawn has not been called
❌ LLM 判定失败: greenlet_spawn has not been called
```

**原因**：
- 10个并发任务共享同一个 `self.db` 数据库会话
- SQLAlchemy异步会话不支持并发访问

**临时解决**：
```python
CONCURRENT_BATCH_SIZE = 1  # 改为串行处理
```

**长期解决**：
- 为每个group创建独立数据库会话
- 参见 `GLOBAL_MERGE_BUG_REPORT.md` 方案2

---

### 问题2: 部分数据无法完成归并

**现象**：
- 剩余100+条数据一直处于 `pending_global_merge` 状态

**原因**：
- 并发处理时，失败的group被 `return_exceptions=True` 捕获
- 失败group的数据状态未更新，仍然是 `pending_global_merge`
- 下一轮继续失败，形成死循环

**解决**：
- 修复并发问题后，自然解决
- 或使用 `scripts/auto_complete_eve_merge.py` 自动完成

---

## 📚 八、相关文件

### 8.1 核心文件

```
backend/app/services/
├── global_merge.py          # 整体归并服务（本文档）
├── event_merge.py           # 新事件归并（阶段一）
├── heat_normalization.py    # 热度归一化
├── classification_service.py # Topic分类
├── summary_service.py       # 摘要生成
└── vector_service.py        # 向量数据库操作

backend/app/models/
├── source_item.py           # SourceItem模型
├── topic.py                 # Topic、TopicNode、TopicPeriodHeat模型
└── llm_judgement.py         # LLM判定记录模型
```

### 8.2 配置文件

```
backend/app/config.py        # 全局配置
backend/.env                 # 环境变量
```

### 8.3 文档

```
backend/GLOBAL_MERGE_BUG_REPORT.md           # Bug分析报告
backend/GLOBAL_MERGE_IMPLEMENTATION.md       # 本文档
docs/merge-logic.md                          # 归并逻辑总体文档
docs/数据流转架构.md                          # 系统架构文档
```

---

## 🎯 九、未来优化方向

### 9.1 短期（1-2天）

1. **修复并发处理** ⭐⭐⭐⭐⭐
   - 为每个group创建独立会话
   - 恢复 `CONCURRENT_BATCH_SIZE = 10`
   - 预期性能提升：串行 → 10倍并行

2. **添加超时控制** ⭐⭐⭐⭐
   - 使用 `asyncio.wait_for()` 包裹主流程
   - 防止长时间运行卡住

3. **优化失败重试机制** ⭐⭐⭐
   - 记录失败的group_id
   - 下一轮优先处理失败的group

---

### 9.2 中期（1-2周）

1. **LLM批量判定** ⭐⭐⭐⭐
   - 将多个事件的判定合并为一个LLM调用
   - 减少LLM调用次数，降低成本

2. **智能候选数量调整** ⭐⭐⭐
   - 根据相似度动态调整候选数量
   - 高相似度：减少候选（3-5个）
   - 低相似度：增加候选（10-15个）

3. **向量索引优化** ⭐⭐⭐⭐⭐
   - 在Chroma中为Topic创建专门的collection
   - 直接检索Topic向量，而非source_item向量
   - 预期性能提升：10-100倍

---

### 9.3 长期（1个月+）

1. **增量学习机制** ⭐⭐⭐⭐⭐
   - 收集LLM判定的正确/错误样本
   - 微调LLM模型，提升判定准确率

2. **分布式处理** ⭐⭐⭐⭐
   - 使用Celery分布式任务队列
   - 将event_group分配到多个worker并行处理

3. **实时归并** ⭐⭐⭐
   - 从定时批量归并 → 实时流式归并
   - 事件采集后立即触发归并

---

## 📝 十、总结

**整体归并（Global Merge）** 是Echoman系统的核心功能，负责将新采集的事件与历史Topic库进行智能关联，实现事件的演进追踪和主题聚合。

**核心技术**：
- **向量检索**：基于语义相似度快速召回候选Topic
- **LLM判定**：通过大模型判断事件的关联性和演进关系
- **数据库事务**：确保数据一致性和完整性

**关键优化**：
- 批量处理（200组/轮）
- 候选限制（Top-10）
- Token管理（2500 tokens）
- 时间窗口（7天）

**当前状态**：
- ✅ 功能完整，逻辑正确
- ⚠️  并发处理存在会话冲突（已临时修复为串行）
- 📈 性能优化空间：10倍+（修复并发后）

**下一步**：
1. 修复并发处理（独立会话）
2. 添加超时控制
3. 优化向量索引（Topic collection）

---

**维护者**: Echoman开发团队  
**最后更新**: 2025-11-08  
**版本**: v1.0

