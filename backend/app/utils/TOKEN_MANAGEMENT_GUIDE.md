# Token 管理指南

## 🎯 背景

**qwen3-32b 模型的上下文限制为 32k tokens**。在使用 AI 服务时，必须合理分配 token 预算，避免超过上下文限制导致请求失败。

---

## 📊 Token 预算分配策略

### 32k 上下文分配建议

```
总上下文: 32,000 tokens
├── 安全边界: 2,000 tokens      (6.25%)  预留给系统overhead
├── 系统Prompt: 500-1,000 tokens (3%)    固定的系统指令
├── 用户查询: 100-500 tokens    (1.5%)  用户问题
├── 检索上下文: 20,000 tokens   (62.5%) 主要内容
└── 生成回复: 2,000-8,000 tokens(25%)   模型生成的答案
```

### 不同场景的分配

| 场景 | 系统Prompt | 查询 | 上下文 | 回复 | 总计 |
|------|-----------|------|--------|------|------|
| **简单问答** | 500 | 200 | 10,000 | 2,000 | 14,700 |
| **RAG对话** | 800 | 300 | 20,000 | 2,000 | 25,100 |
| **摘要生成** | 600 | 100 | 15,000 | 5,000 | 20,700 |
| **分类判断** | 400 | 200 | 5,000 | 500 | 6,100 |
| **长文本生成** | 500 | 200 | 8,000 | 8,000 | 16,700 |

---

## 🛠️ 使用 TokenManager

### 基本使用

```python
from app.utils.token_manager import TokenManager

# 创建 token 管理器
token_manager = TokenManager(model="qwen3-32b")

# 计算文本 token 数
text = "这是一段测试文本"
token_count = token_manager.count_tokens(text)
print(f"Token 数量: {token_count}")
```

### RAG 上下文优化

```python
# 优化 RAG 上下文
query = "最近有什么热点事件？"
context_chunks = [
    {"content": "新闻1的内容...", "id": 1},
    {"content": "新闻2的内容...", "id": 2},
    {"content": "新闻3的内容...", "id": 3},
    # ... 更多上下文
]

# 自动截断，确保不超过限制
optimized_chunks, stats = token_manager.optimize_rag_context(
    query=query,
    context_chunks=context_chunks,
    system_prompt_template="你是一个热点新闻助手...",
    max_completion_tokens=2000
)

print(f"原始块数: {stats['original_chunks']}")
print(f"优化后块数: {stats['optimized_chunks']}")
print(f"使用的上下文tokens: {stats['used_context_tokens']}")
print(f"可用的上下文tokens: {stats['available_context_tokens']}")
```

### 手动截断文本

```python
# 截断长文本
long_text = "很长很长的文本..." * 1000

# 截断到 5000 tokens，保留开头
truncated = token_manager.truncate_text(
    text=long_text,
    max_tokens=5000,
    keep_start=True
)

# 截断到 3000 tokens，保留结尾
truncated_end = token_manager.truncate_text(
    text=long_text,
    max_tokens=3000,
    keep_start=False
)
```

### 计算可用上下文

```python
# 计算还能用多少 tokens 放上下文
available = token_manager.calculate_available_context_tokens(
    system_prompt="你是一个助手...",
    user_query="用户的问题",
    max_completion_tokens=2000
)

print(f"可用于上下文的tokens: {available}")
```

---

## ⚙️ 配置说明

### settings.py 中的相关配置

```python
# LLM 调用配置
llm_max_tokens: int = 2048              # 单次回复最大tokens
llm_context_limit: int = 32000          # 总上下文限制
llm_safety_margin: int = 2000           # 安全边界

# RAG 配置
rag_max_context_tokens: int = 20000     # RAG最大上下文tokens
rag_max_completion_tokens: int = 2000   # 生成回复最大tokens
rag_enable_token_optimization: bool = True  # 启用token优化
```

### 修改配置

创建 `.env` 文件覆盖默认值：

```bash
# .env
LLM_CONTEXT_LIMIT=32000
RAG_MAX_CONTEXT_TOKENS=20000
RAG_MAX_COMPLETION_TOKENS=2000
```

---

## 📝 最佳实践

### 1. 总是启用 Token 优化

```python
# ✅ 好的做法
if settings.rag_enable_token_optimization:
    optimized_chunks, _ = token_manager.optimize_rag_context(...)
else:
    optimized_chunks = context_chunks

# ❌ 不好的做法
# 直接使用所有检索结果，可能超过限制
context = "\n".join([chunk["content"] for chunk in all_chunks])
```

### 2. 分级处理长文本

```python
# 根据重要性排序，优先保留重要内容
sorted_chunks = sorted(
    context_chunks,
    key=lambda x: x.get("relevance_score", 0),
    reverse=True
)

# 然后进行 token 优化
optimized_chunks, _ = token_manager.optimize_rag_context(
    query=query,
    context_chunks=sorted_chunks,
    max_completion_tokens=2000
)
```

### 3. 监控 Token 使用情况

```python
# 记录 token 统计
_, stats = token_manager.optimize_rag_context(...)

logger.info(f"Token使用统计: {stats}")

# 如果经常接近限制，考虑调整策略
if stats['used_context_tokens'] > stats['available_context_tokens'] * 0.9:
    logger.warning("Token使用接近限制，考虑减少检索数量")
```

### 4. 针对不同任务优化

```python
# 摘要任务：多给生成空间
summary_optimized, _ = token_manager.optimize_rag_context(
    query=query,
    context_chunks=chunks,
    max_completion_tokens=5000  # 摘要需要更多生成空间
)

# 分类任务：少量生成即可
classification_optimized, _ = token_manager.optimize_rag_context(
    query=query,
    context_chunks=chunks,
    max_completion_tokens=500  # 分类只需要简短回复
)
```

---

## 🚨 常见陷阱

### ❌ 陷阱 1: 忽略系统 Prompt

```python
# 错误：没有计入系统 prompt 的 tokens
max_context = 32000 - 2000  # 只减去安全边界

# 正确：计入所有固定内容
system_prompt_tokens = token_manager.count_tokens(system_prompt)
max_context = 32000 - 2000 - system_prompt_tokens - query_tokens - max_completion_tokens
```

### ❌ 陷阱 2: 过度估算

```python
# 错误：过度保守，浪费上下文空间
max_context = 32000 // 4  # 只用 25%

# 正确：合理分配
max_context = 32000 - safety_margin - fixed_costs
```

### ❌ 陷阱 3: 没有降级策略

```python
# 错误：检索失败就直接报错
if not context_chunks:
    raise ValueError("没有检索到内容")

# 正确：有降级方案
if not context_chunks:
    return fallback_answer(query)
```

---

## 📊 Token 计数规则

### 中英文混合估算

```python
# 规则：
# - 纯英文：约 4 字符 = 1 token
# - 纯中文：约 1.5 字符 = 1 token
# - 混合：约 2 字符 = 1 token（保守估计）

# 示例
text1 = "Hello world"  # 约 3 tokens
text2 = "你好世界"    # 约 3 tokens
text3 = "Hello 世界"  # 约 3 tokens
```

### 精确 vs 估算

```python
# 精确计数（需要 tiktoken）
token_manager = TokenManager(model="qwen3-32b")
exact_count = token_manager.count_tokens(text)

# 快速估算（不依赖 tiktoken）
from app.utils.token_manager import estimate_tokens_simple
approx_count = estimate_tokens_simple(text)

# 估算误差通常在 ±10% 以内
```

---

## 🎓 进阶技巧

### 1. 动态调整检索数量

```python
# 根据 token 限制动态调整检索数量
def adaptive_retrieval(query, initial_topk=10):
    token_manager = TokenManager(model="qwen3-32b")
    available_tokens = token_manager.calculate_available_context_tokens(
        system_prompt=SYSTEM_PROMPT,
        user_query=query,
        max_completion_tokens=2000
    )
    
    # 估算每个chunk的平均token数
    avg_chunk_tokens = 2000  # 根据实际数据调整
    
    # 动态调整topk
    adjusted_topk = min(initial_topk, available_tokens // avg_chunk_tokens)
    
    return retrieve_chunks(query, topk=adjusted_topk)
```

### 2. 渐进式添加上下文

```python
# 优先级排序后，逐个添加直到接近限制
def progressive_context_building(chunks, max_tokens):
    token_manager = TokenManager(model="qwen3-32b")
    selected_chunks = []
    total_tokens = 0
    
    for chunk in sorted_chunks_by_priority(chunks):
        chunk_tokens = token_manager.count_tokens(chunk["content"])
        
        if total_tokens + chunk_tokens <= max_tokens * 0.95:  # 留5%缓冲
            selected_chunks.append(chunk)
            total_tokens += chunk_tokens
        else:
            break
    
    return selected_chunks, total_tokens
```

### 3. 分段处理超长文档

```python
# 对于超长文档，分段处理
def process_long_document(document, chunk_size=15000):
    token_manager = TokenManager(model="qwen3-32b")
    
    # 分段
    segments = []
    current_segment = ""
    current_tokens = 0
    
    for paragraph in document.split("\n\n"):
        para_tokens = token_manager.count_tokens(paragraph)
        
        if current_tokens + para_tokens <= chunk_size:
            current_segment += paragraph + "\n\n"
            current_tokens += para_tokens
        else:
            if current_segment:
                segments.append(current_segment)
            current_segment = paragraph + "\n\n"
            current_tokens = para_tokens
    
    if current_segment:
        segments.append(current_segment)
    
    # 分别处理每段
    results = []
    for segment in segments:
        result = process_segment(segment)
        results.append(result)
    
    # 合并结果
    return merge_results(results)
```

---

## 📖 相关文档

- [RAG 服务实现](../services/rag_service.py)
- [配置说明](../config/settings.py)
- [LLM Provider](../services/llm/)

---

**最后更新**: 2025-10-30  
**适用模型**: qwen3-32b (32k context)

