# RAG 对话系统实现逻辑

## 📋 目录

1. [系统架构](#系统架构)
2. [核心流程](#核心流程)
3. [两种对话模式](#两种对话模式)
4. [关键组件](#关键组件)
5. [技术细节](#技术细节)

---

## 🏗️ 系统架构

```
┌─────────────┐
│  前端请求    │
│ (SSE/JSON)  │
└──────┬──────┘
       │
       ▼
┌─────────────────────┐
│   API 层            │
│ /api/v1/chat/ask   │
└──────┬──────────────┘
       │
       ▼
┌─────────────────────┐
│   RAG Service       │
│ ┌─────────────────┐ │
│ │ 1. 参数验证     │ │
│ │ 2. 检索上下文   │ │
│ │ 3. Token优化    │ │
│ │ 4. 构建Prompt   │ │
│ │ 5. LLM调用      │ │
│ │ 6. 返回结果     │ │
│ └─────────────────┘ │
└──────┬──────────────┘
       │
       ├───────────────┬────────────┐
       ▼               ▼            ▼
┌──────────┐    ┌──────────┐  ┌──────────┐
│ Vector   │    │ Token    │  │ LLM      │
│ Search   │    │ Manager  │  │ Provider │
└──────────┘    └──────────┘  └──────────┘
```

---

## 🔄 核心流程

### 1. **接收请求** (`/api/v1/chat/ask`)

```python
POST /api/v1/chat/ask
{
    "query": "用户问题",
    "mode": "topic" | "global",
    "topic_id": 123,  // topic模式必需
    "stream": true    // 是否流式输出
}
```

### 2. **RAG 处理流程**

```python
async def ask(query, mode, topic_id, chat_id):
    # ① 参数验证
    if mode == "topic" and not topic_id:
        raise ValueError("topic模式需要提供topic_id")
    
    # ② 检索相关上下文
    if mode == "topic":
        context, citations = await _retrieve_topic_context(db, topic_id, query)
    else:
        context, citations = await _retrieve_global_context(db, query)
    
    # ③ 降级处理
    if not context:
        return await _fallback_answer(query, mode)
    
    # ④ 格式化上下文
    formatted_context = _format_context_chunks(context)
    
    # ⑤ Token 优化（确保不超过32k限制）
    optimized_context, token_stats = token_manager.optimize_rag_context(
        query=query,
        context_chunks=formatted_context,
        system_prompt=_get_system_prompt(mode),
        max_completion_tokens=2000
    )
    
    # ⑥ 构建 RAG Prompt
    prompt = _build_rag_prompt(query, optimized_context, mode)
    
    # ⑦ 调用 LLM
    response = await llm_provider.chat_completion(
        messages=[{"role": "user", "content": prompt}],
        temperature=0.7,
        max_tokens=2000
    )
    
    # ⑧ 解析和返回
    answer = _parse_answer(response)
    return {
        "answer": answer,
        "citations": citations,
        "diagnostics": {...}
    }
```

---

## 🎯 两种对话模式

### **模式 1: Topic 模式（事件模式）**

**使用场景**：针对特定热点事件的深度问答

**检索逻辑**：

```python
async def _retrieve_topic_context(db, topic_id, query):
    # 1. 获取主题基本信息
    topic = await db.get(Topic, topic_id)
    
    # 2. 获取主题摘要
    summary = await db.get(Summary, topic.summary_id)
    
    # 3. 向量检索最相关的节点（TopK=5）
    query_embedding = await _get_query_embedding(query)
    relevant_nodes = await _vector_search_nodes(
        db, topic_id, query_embedding, limit=5
    )
    
    # 4. 构造上下文
    context = []
    
    # 添加摘要
    if summary:
        context.append({
            "type": "summary",
            "content": summary.content
        })
    
    # 添加相关节点
    for node in relevant_nodes:
        context.append({
            "type": "node",
            "platform": node.source_item.platform,
            "title": node.source_item.title,
            "summary": node.source_item.summary,
            "url": node.source_item.url
        })
    
    return context, citations
```

**向量检索**：

```sql
-- 使用 pgvector 进行余弦相似度搜索
SELECT n.id, (e.vector <=> query_vector::vector) as distance
FROM topic_nodes n
JOIN embeddings e ON e.object_type = 'node' AND e.object_id = n.id
WHERE n.topic_id = :topic_id
  AND (e.vector <=> query_vector::vector) < 0.7  -- 相似度阈值
ORDER BY distance ASC
LIMIT 5
```

### **模式 2: Global 模式（自由模式）**

**使用场景**：跨事件的全局检索和对比

**检索逻辑**：

```python
async def _retrieve_global_context(db, query):
    # 1. 向量检索相关主题（TopK=10）
    query_embedding = await _get_query_embedding(query)
    relevant_topics = await _vector_search_topics(
        db, query_embedding, limit=10
    )
    
    # 2. 构造上下文
    context = []
    
    for topic in relevant_topics:
        # 获取主题摘要
        summary = await db.get(Summary, topic.summary_id)
        if summary:
            context.append({
                "type": "topic_summary",
                "topic_title": topic.title_key,
                "content": summary.content,
                "intensity": topic.intensity_total,
                "first_seen": topic.first_seen
            })
        
        # 获取该主题的代表性节点
        nodes = await _get_latest_nodes(db, topic.id, limit=2)
        for node in nodes:
            context.append({
                "type": "node",
                "topic_title": topic.title_key,
                "platform": node.source_item.platform,
                "title": node.source_item.title,
                "summary": node.source_item.summary
            })
    
    return context, citations
```

**向量检索**：

```sql
-- 检索主题摘要的向量相似度
SELECT t.id, (e.vector <=> query_vector::vector) as distance
FROM topics t
JOIN summaries s ON s.id = t.summary_id
JOIN embeddings e ON e.object_type = 'topic_summary' AND e.object_id = s.id
WHERE t.status = 'active'
ORDER BY distance ASC
LIMIT 10
```

---

## 🔧 关键组件

### 1. **Token Manager** - Token 管理和优化

**核心功能**：
- 计算 Token 数量（使用 tiktoken）
- 优化上下文避免超过模型限制（32k）
- 智能截断和保留最相关内容

```python
class TokenManager:
    MODEL_CONTEXT_LIMITS = {
        "qwen3-32b": 32000,
        "gpt-4o": 128000,
        ...
    }
    
    def optimize_rag_context(
        self,
        query: str,
        context_chunks: List[Dict],
        system_prompt_template: str,
        max_completion_tokens: int = 2000
    ):
        """
        优化 RAG 上下文
        
        计算逻辑：
        available_tokens = model_limit - system_tokens - query_tokens - max_completion
        
        返回：
        - optimized_chunks: 优化后的上下文块
        - token_stats: Token 使用统计
        """
        # 1. 计算各部分 token
        query_tokens = self.count_tokens(query)
        system_tokens = self.count_tokens(system_prompt_template)
        
        # 2. 计算可用 token
        available = (
            self.context_limit 
            - self.SAFETY_MARGIN 
            - system_tokens 
            - query_tokens 
            - max_completion_tokens
        )
        
        # 3. 根据可用 token 截断上下文
        optimized_chunks = []
        used_tokens = 0
        
        for chunk in context_chunks:
            chunk_tokens = self.count_tokens(chunk["content"])
            if used_tokens + chunk_tokens <= available:
                optimized_chunks.append(chunk)
                used_tokens += chunk_tokens
            else:
                # 截断最后一个块
                remaining = available - used_tokens
                if remaining > 100:  # 至少保留100 tokens
                    truncated = self.truncate_text(
                        chunk["content"], 
                        remaining
                    )
                    optimized_chunks.append({
                        **chunk, 
                        "content": truncated
                    })
                break
        
        return optimized_chunks, {
            "original_chunks": len(context_chunks),
            "optimized_chunks": len(optimized_chunks),
            "used_context_tokens": used_tokens,
            "available_context_tokens": available
        }
```

### 2. **LLM Provider** - 多模型支持

**支持的提供商**：
- Qwen (通义千问)
- OpenAI
- Azure OpenAI
- OpenAI Compatible (任何兼容接口)

```python
class BaseLLMProvider:
    async def chat_completion(
        self, 
        messages: List[Dict], 
        temperature: float, 
        max_tokens: int
    ) -> str:
        """标准对话完成接口"""
        
    async def chat_completion_stream(
        self,
        messages: List[Dict],
        temperature: float,
        max_tokens: int
    ) -> AsyncGenerator[Dict, None]:
        """流式对话完成接口（SSE）"""
        
    async def embedding(self, text: str) -> List[float]:
        """文本向量化接口"""
```

**工厂模式创建**：

```python
def get_llm_provider(provider_name: str, model: str):
    if provider_name == "qwen":
        return QwenProvider(
            model=model,
            api_key=settings.qwen_api_key,
            base_url=settings.qwen_api_base
        )
    elif provider_name == "openai":
        return OpenAIProvider(...)
    # ...
```

### 3. **向量检索** - pgvector 实现

**数据库设置**：

```sql
-- 启用 pgvector 扩展
CREATE EXTENSION IF NOT EXISTS vector;

-- embeddings 表
CREATE TABLE embeddings (
    id BIGSERIAL PRIMARY KEY,
    object_type VARCHAR(50),  -- 'node', 'topic_summary'
    object_id BIGINT,
    vector vector(1536),      -- OpenAI ada-002 维度
    model VARCHAR(100),
    created_at TIMESTAMP
);

-- 创建向量索引（HNSW 算法，快速近似搜索）
CREATE INDEX idx_embeddings_vector ON embeddings 
USING hnsw (vector vector_cosine_ops);
```

**检索查询**：

```python
# 余弦相似度检索 (pgvector)
stmt = text("""
    SELECT n.id, (e.vector <=> :query_vector::vector) as distance
    FROM topic_nodes n
    JOIN embeddings e ON e.object_type = 'node' AND e.object_id = n.id
    WHERE n.topic_id = :topic_id
    ORDER BY distance ASC
    LIMIT :limit
""")

result = await db.execute(stmt, {
    "query_vector": f"[{','.join(map(str, query_embedding))}]",
    "topic_id": topic_id,
    "limit": 5
})
```

**相似度计算**：
- `<=>` 运算符：余弦距离（越小越相似）
- 阈值：0.7（距离 > 0.7 的会被过滤）

---

## 🚀 技术细节

### 1. **流式输出（SSE）**

```python
async def ask_stream(db, query, mode, topic_id):
    """
    SSE 事件流格式：
    event: token
    data: {"content": "文"}
    
    event: token  
    data: {"content": "字"}
    
    event: citations
    data: {"citations": [...]}
    
    event: done
    data: {"diagnostics": {...}}
    """
    # 检索上下文
    context, citations = await _retrieve_context(...)
    
    # 构建 prompt
    prompt = _build_rag_prompt(query, context, mode)
    
    # 流式调用 LLM
    full_answer = ""
    async for chunk in llm_provider.chat_completion_stream(
        messages=[{"role": "user", "content": prompt}],
        temperature=0.7
    ):
        content = chunk.get("content", "")
        if content:
            full_answer += content
            
            # 发送 token 事件
            yield {
                "type": "token",
                "data": {"content": content}
            }
    
    # 发送引用
    yield {
        "type": "citations",
        "data": {"citations": citations}
    }
    
    # 发送完成信号
    yield {
        "type": "done",
        "data": {"diagnostics": {...}}
    }
```

**前端接收**：

```typescript
const response = await fetch('/api/v1/chat/ask', {
    method: 'POST',
    body: JSON.stringify({ query, mode, stream: true })
});

const reader = response.body.getReader();
const decoder = new TextDecoder();
let buffer = "";
let currentEvent = "";

while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    
    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    buffer = lines.pop() || "";
    
    for (const line of lines) {
        if (line.startsWith("event:")) {
            currentEvent = line.substring(6).trim();
        }
        if (line.startsWith("data:")) {
            const data = JSON.parse(line.substring(5).trim());
            
            if (currentEvent === "token") {
                onToken(data.content);  // 逐字显示
            } else if (currentEvent === "citations") {
                onCitations(data.citations);
            } else if (currentEvent === "done") {
                onDone(data.diagnostics);
            }
        }
    }
}
```

### 2. **Prompt 工程**

**Topic 模式 Prompt**：

```
请基于以下主题内容回答用户问题：

【参考内容】
【主题摘要】
王传君获东京电影节影帝...

1. [今日头条] 2025/11/04
   王传君获东京电影节影帝
   日本东京电影节闭幕，王传君凭借...

2. [微博] 2025/11/04
   ...

【用户问题】
王传君在东京电影节获得了什么奖项？

要求：
1. 基于提供的参考内容回答，不要编造信息
2. 如果参考内容不足以回答问题，明确说明
3. 回答要准确、简洁、有条理
4. 可以引用具体的来源（如"根据微博消息..."）

请回答：
```

**Global 模式 Prompt**：

```
请基于以下检索到的相关内容回答用户问题：

【参考内容】（按相关性排序）
【主题1：王传君获东京电影节影帝】
摘要：王传君获得东京电影节最佳男演员...
回声强度：8250

1. [今日头条] 2025/11/04
   王传君获东京电影节影帝
   ...

【主题2：2026春节放9天假】
摘要：国务院发布2026年节假日安排...
回声强度：6800

【用户问题】
最近有哪些热点事件？

要求：
1. 综合多个主题的信息回答
2. 如果没有找到相关内容，明确告知用户
3. 回答要准确、客观、有条理
4. 可以引用具体的主题或来源

请回答：
```

### 3. **对话历史管理**

**设计理念**：对话上下文在前端维护，无需持久化存储

**前端实现**：

```typescript
// ConversationConsole.tsx
const [messages, setMessages] = useState<Message[]>([]);

// 消息类型
interface Message {
  id: string;
  role: "user" | "assistant" | "timeline";
  text: string;
  timestamp: Date;
  // 仅用于时间线消息
  summary?: string;
  keyPoints?: string[];
  timelineNodes?: TimelineNode[];
}

// 添加用户消息
const addUserMessage = (text: string) => {
  setMessages(prev => [...prev, {
    id: Date.now().toString(),
    role: "user",
    text,
    timestamp: new Date()
  }]);
};

// 添加助手消息（流式）
const addAssistantMessage = (id: string, chunk: string) => {
  setMessages(prev => {
    const lastMsg = prev[prev.length - 1];
    if (lastMsg?.id === id && lastMsg.role === "assistant") {
      // 追加到现有消息
      return [...prev.slice(0, -1), {
        ...lastMsg,
        text: lastMsg.text + chunk
      }];
    } else {
      // 创建新消息
      return [...prev, {
        id,
        role: "assistant",
        text: chunk,
        timestamp: new Date()
      }];
    }
  });
};

// 刷新对话（重置到初始状态）
const handleRefresh = () => {
  setMessages(buildInitialMessages());
  setInput("");
};
```

**优点**：
- ✅ **轻量级**：无需数据库存储，减少后端负担
- ✅ **实时性**：对话状态即时响应，无延迟
- ✅ **隐私性**：对话不持久化，保护用户隐私
- ✅ **灵活性**：刷新即可重置，用户体验更好

**数据库表**（保留但不使用）：

```python
# chats 表（保留用于未来扩展，如对话记录功能）
chats:
  - id: 会话ID
  - mode: 'topic' | 'global'
  - topic_id: 关联主题ID（topic模式）
  - created_at: 创建时间

# 当前版本不再存储 chat_messages 和 citations
```

### 4. **降级策略**

```python
# 1. 向量检索失败 -> 使用时间排序
if not query_embedding:
    relevant_nodes = await _get_latest_nodes(db, topic_id, limit=5)

# 2. 没有检索到内容 -> 返回友好提示
if not context:
    return {
        "answer": "抱歉，暂时没有找到相关信息。",
        "citations": [],
        "diagnostics": {"fallback": True}
    }

# 3. LLM 调用失败 -> 返回错误信息
except Exception as e:
    return {
        "answer": f"抱歉，回答生成失败：{str(e)}",
        "citations": [],
        "diagnostics": {"error": True}
    }
```

---

## 📊 性能优化

### Token 优化效果

```python
# 示例统计
{
    "original_chunks": 15,           # 原始检索到15个块
    "optimized_chunks": 8,           # 优化后保留8个
    "used_context_tokens": 28000,    # 使用28k tokens
    "available_context_tokens": 28500, # 可用28.5k tokens
    "tokens_prompt": 29000,          # 总prompt tokens
    "tokens_completion": 450,        # 回答 tokens
    "latency_ms": 3200              # 延迟3.2秒
}
```

### 向量检索性能

```
HNSW 索引（10万条数据）:
- TopK=5: ~10ms
- TopK=10: ~15ms
- TopK=20: ~25ms

暴力检索（10万条数据）:
- TopK=5: ~500ms
- TopK=10: ~800ms
```

---

## 🎓 总结

**RAG 系统核心优势**：
1. ✅ **准确性**：基于实际数据回答，避免幻觉
2. ✅ **可追溯**：提供引用来源，用户可验证
3. ✅ **实时性**：检索最新数据，不受模型训练时间限制
4. ✅ **可扩展**：支持多种 LLM 和向量模型

**关键技术点**：
- 🔍 向量检索（pgvector + HNSW）
- 🎯 Token 管理（确保不超限）
- 🔄 流式输出（SSE）
- 📦 多模式支持（topic/global）
- 🛡️ 降级策略（失败友好处理）

**适用场景**：
- ✅ 知识问答
- ✅ 文档检索
- ✅ 内容总结
- ✅ 多源信息整合

---

## 💡 前端交互优化

### 1. **对话模式优化**

**事件模式（Event Mode）**：
- 专注于事件时间线展示
- 隐藏输入框，只显示时间线
- 点击事件自动刷新对话并展示时间线
- 适合快速浏览事件详情

**自由模式（Free Mode）**：
- 全局检索和问答
- 显示输入框，支持自由提问
- 基于全局数据提供答案
- 适合跨事件的信息查询

```typescript
// 默认为事件模式
const [mode, setMode] = useState<"free" | "event">("event");

// 条件渲染输入框
{mode === "free" && (
  <div className="conversation-input">
    <textarea ... />
    <button>发送</button>
  </div>
)}
```

### 2. **交互功能**

**刷新按钮**：
- 位置：对话标题右侧
- 功能：重置对话到初始状态
- 快捷操作：清空输入框和消息历史

**Enter发送**：
- Enter键：发送消息
- Shift+Enter：换行
- 提升输入效率

```typescript
const handleTextareaKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    handleSubmit();
  }
};
```

**自动滚动**：
- 新消息出现时自动滚动到底部
- 流式输出时实时滚动
- 提供流畅的对话体验

```typescript
const messagesEndRef = useRef<HTMLDivElement | null>(null);

const scrollToBottom = () => {
  messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
};

useEffect(() => {
  scrollToBottom();
}, [messages]);
```

### 3. **UI/UX 设计**

**玻璃拟态设计（Glassmorphism）**：
```css
.conversation-input {
  background: linear-gradient(
    150deg, 
    rgba(30, 41, 59, 0.78), 
    rgba(15, 23, 42, 0.84)
  );
  backdrop-filter: blur(18px);
  border: 1px solid rgba(148, 163, 184, 0.18);
  box-shadow: 0 24px 55px rgba(15, 23, 42, 0.4);
}
```

**紧凑布局**：
- 减少时间线卡片间距（gap: 12px → 8px）
- 优化内边距（padding: 20px → 16px）
- 缩小字号（14px → 13px）
- 提升信息密度，减少滚动

**视觉统一**：
- 标题加粗统一（font-weight: 700）
- 字号统一（20px）
- 数据源文字不加粗（font-weight: 400）
- 保持视觉层级清晰

