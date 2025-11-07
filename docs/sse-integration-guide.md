# SSE流式对话集成指南

## 概述

Echoman系统已完成SSE（Server-Sent Events）流式对话功能的开发。本文档提供完整的集成指南和使用示例。

## 功能特性

- ✅ 实时流式输出AI回答
- ✅ 逐字显示效果
- ✅ 引用来源展示
- ✅ 诊断信息反馈
- ✅ 错误处理机制
- ✅ 连接管理

## 后端API

### 端点

```
POST /api/v1/chat/ask
```

### 请求参数

```typescript
{
  "query": string,          // 用户问题
  "mode": "topic" | "global", // 对话模式
  "topic_id"?: number,      // 主题ID（topic模式必需）
  "chat_id"?: number,       // 会话ID（可选）
  "stream": true            // 启用流式输出
}
```

### 响应格式

SSE事件流，包含以下事件类型：

#### 1. token事件（逐字输出）

```
event: token
data: {"content":"这"}

event: token
data: {"content":"是"}

event: token
data: {"content":"流"}

event: token
data: {"content":"式"}

event: token
data: {"content":"输"}

event: token
data: {"content":"出"}
```

#### 2. citations事件（引用来源）

```
event: citations
data: {
  "citations": [
    {
      "topic_id": 123,
      "node_id": 456,
      "source_url": "https://...",
      "snippet": "引用片段...",
      "platform": "weibo"
    }
  ]
}
```

#### 3. done事件（完成信号）

```
event: done
data: {
  "diagnostics": {
    "latency_ms": 1520,
    "tokens_prompt": 1200,
    "tokens_completion": 180,
    "context_chunks": 5,
    "original_chunks": 10
  }
}
```

#### 4. error事件（错误信息）

```
event: error
data: {"message": "错误描述"}
```

## 前端集成

### TypeScript集成（推荐）

我们已经提供了完整的TypeScript集成代码：

```typescript
// frontend/src/services/sse.ts
import { startSSEStream } from './services/sse';

const cleanup = await startSSEStream({
  query: "最近有什么热点新闻？",
  mode: "global",
  
  // 逐字接收回答
  onToken: (content) => {
    console.log(content); // 输出每个字符
    // 更新UI显示
  },
  
  // 接收引用来源
  onCitations: (citations) => {
    console.log("引用来源:", citations);
    // 显示引用信息
  },
  
  // 接收完成信号
  onDone: (diagnostics) => {
    console.log("对话完成，诊断信息:", diagnostics);
    // 显示统计信息
  },
  
  // 错误处理
  onError: (message) => {
    console.error("错误:", message);
    // 显示错误提示
  },
});

// 取消连接
// cleanup();
```

### React组件示例

```tsx
import React, { useState } from 'react';
import { startSSEStream } from '../services/sse';

export const ChatComponent: React.FC = () => {
  const [query, setQuery] = useState("");
  const [answer, setAnswer] = useState("");
  const [citations, setCitations] = useState([]);
  const [isLoading, setIsLoading] = useState(false);
  
  const handleAsk = async () => {
    if (!query.trim()) return;
    
    setIsLoading(true);
    setAnswer("");
    setCitations([]);
    
    const cleanup = await startSSEStream({
      query,
      mode: "global",
      
      onToken: (content) => {
        setAnswer(prev => prev + content);
      },
      
      onCitations: (cites) => {
        setCitations(cites);
      },
      
      onDone: (diagnostics) => {
        setIsLoading(false);
        console.log("延迟:", diagnostics.latency_ms, "ms");
      },
      
      onError: (message) => {
        setIsLoading(false);
        alert("错误: " + message);
      },
    });
  };
  
  return (
    <div>
      <input
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        placeholder="输入你的问题..."
      />
      <button onClick={handleAsk} disabled={isLoading}>
        {isLoading ? "生成中..." : "发送"}
      </button>
      
      <div className="answer">
        {answer}
      </div>
      
      {citations.length > 0 && (
        <div className="citations">
          <h4>引用来源：</h4>
          {citations.map((cite, idx) => (
            <div key={idx}>
              <a href={cite.source_url} target="_blank">
                {cite.platform} - {cite.snippet}
              </a>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};
```

### 原生JavaScript示例

```javascript
async function askQuestion(query) {
  const url = "http://localhost:8778/api/v1/chat/ask";
  
  const response = await fetch(url, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      query: query,
      mode: "global",
      stream: true,
    }),
  });
  
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let currentEvent = null;
  
  while (true) {
    const { done, value } = await reader.read();
    
    if (done) break;
    
    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    buffer = lines.pop() || "";
    
    for (const line of lines) {
      const trimmed = line.trim();
      
      if (!trimmed) {
        currentEvent = null;
        continue;
      }
      
      if (trimmed.startsWith("event:")) {
        currentEvent = trimmed.substring(6).trim();
      } else if (trimmed.startsWith("data:")) {
        const dataStr = trimmed.substring(5).trim();
        const data = JSON.parse(dataStr);
        
        if (currentEvent === "token") {
          console.log(data.content); // 输出每个字符
        } else if (currentEvent === "citations") {
          console.log("引用:", data.citations);
        } else if (currentEvent === "done") {
          console.log("完成:", data.diagnostics);
        } else if (currentEvent === "error") {
          console.error("错误:", data.message);
        }
      }
    }
  }
}

// 使用示例
askQuestion("最近有什么热点新闻？");
```

## 测试

### 后端测试脚本

我们提供了完整的后端测试脚本：

```bash
cd /root/ren/Echoman/backend
conda run -n echoman python test_sse_stream.py
```

### 测试输出示例

```
============================================================
  SSE流式对话测试
============================================================

🚀 开始测试SSE流式对话...
📤 请求: {"query": "最近有什么热点新闻？", "mode": "global", "stream": true}
------------------------------------------------------------
✅ 连接成功，开始接收事件流...

根据最近的数据...（逐字输出）

📚 引用来源:
  [1] weibo: https://...
      片段内容...

✅ 完成!
⏱️  延迟: 1520ms
📊 Token (prompt): 1200
📊 Token (completion): 180
📄 使用的上下文块: 5

------------------------------------------------------------
```

## 性能优化

### 1. 连接管理

```typescript
let currentCleanup: (() => void) | null = null;

async function ask(query: string) {
  // 取消之前的请求
  if (currentCleanup) {
    currentCleanup();
  }
  
  // 发起新请求
  currentCleanup = await startSSEStream({
    query,
    mode: "global",
    // ...callbacks
  });
}
```

### 2. 防抖处理

```typescript
import { debounce } from 'lodash';

const debouncedAsk = debounce(ask, 500);
```

### 3. 打字效果优化

```typescript
let displayQueue: string[] = [];
let isDisplaying = false;

onToken: (content) => {
  displayQueue.push(content);
  if (!isDisplaying) {
    displayNext();
  }
},

async function displayNext() {
  if (displayQueue.length === 0) {
    isDisplaying = false;
    return;
  }
  
  isDisplaying = true;
  const content = displayQueue.shift();
  setAnswer(prev => prev + content);
  
  await new Promise(resolve => setTimeout(resolve, 30)); // 30ms延迟
  displayNext();
}
```

## 错误处理

### 常见错误及解决方案

#### 1. 连接超时

```typescript
const TIMEOUT = 60000; // 60秒超时

const timeoutId = setTimeout(() => {
  cleanup();
  onError("请求超时");
}, TIMEOUT);

onDone: (diagnostics) => {
  clearTimeout(timeoutId);
  // ...
}
```

#### 2. 网络中断

```typescript
onError: (message) => {
  if (message.includes("network") || message.includes("fetch")) {
    // 显示网络错误提示
    showNetworkError();
  } else {
    // 显示一般错误
    showGeneralError(message);
  }
}
```

#### 3. 数据解析失败

后端已内置错误处理，会发送error事件：

```typescript
onError: (message) => {
  console.error("后端错误:", message);
  // 显示用户友好的错误提示
}
```

## 兼容性

- ✅ Chrome/Edge 85+
- ✅ Firefox 80+
- ✅ Safari 14+
- ✅ 移动端浏览器
- ⚠️ IE不支持（已弃用）

## 配置

### 环境变量

```env
# .env.development
VITE_API_BASE_URL=http://localhost:8778/api/v1

# .env.production
VITE_API_BASE_URL=https://api.echoman.com/api/v1
```

### Nginx配置（生产环境）

```nginx
location /api/v1/chat/ask {
    proxy_pass http://backend:8778;
    proxy_http_version 1.1;
    proxy_set_header Connection "";
    proxy_buffering off;
    proxy_cache off;
    proxy_read_timeout 600s;
}
```

## 最佳实践

1. **及时清理连接**：在组件卸载时调用cleanup函数
2. **防止重复请求**：同一时间只保持一个流式连接
3. **用户反馈**：显示加载状态和进度提示
4. **错误提示**：提供友好的错误信息和重试选项
5. **性能监控**：记录诊断信息用于性能分析

## 状态管理

### 推荐的状态结构

```typescript
interface ChatState {
  query: string;
  answer: string;
  citations: Citation[];
  diagnostics: Diagnostics | null;
  isStreaming: boolean;
  error: string | null;
}
```

### 完整状态管理示例

```typescript
const [state, setState] = useState<ChatState>({
  query: "",
  answer: "",
  citations: [],
  diagnostics: null,
  isStreaming: false,
  error: null,
});

const handleAsk = async () => {
  setState(prev => ({
    ...prev,
    answer: "",
    citations: [],
    diagnostics: null,
    isStreaming: true,
    error: null,
  }));
  
  const cleanup = await startSSEStream({
    query: state.query,
    mode: "global",
    
    onToken: (content) => {
      setState(prev => ({
        ...prev,
        answer: prev.answer + content,
      }));
    },
    
    onCitations: (citations) => {
      setState(prev => ({
        ...prev,
        citations,
      }));
    },
    
    onDone: (diagnostics) => {
      setState(prev => ({
        ...prev,
        diagnostics,
        isStreaming: false,
      }));
    },
    
    onError: (message) => {
      setState(prev => ({
        ...prev,
        error: message,
        isStreaming: false,
      }));
    },
  });
};
```

## 后续优化

- [ ] 添加消息历史管理
- [ ] 支持多轮对话上下文
- [ ] 添加流式输出的暂停/恢复功能
- [ ] 实现自动重连机制
- [ ] 添加引用来源的高亮显示

## 支持

如有问题，请查看：
- 后端日志：`/tmp/backend.log`
- 前端控制台：浏览器开发者工具
- API文档：http://localhost:8778/docs

## 更新日志

### 2025-10-31
- ✅ 完成后端SSE流式对话实现
- ✅ 完成前端TypeScript集成代码
- ✅ 添加完整的测试脚本
- ✅ 编写集成文档

---

**状态**: ✅ 已完成  
**优先级**: P0（最高）  
**测试状态**: 通过  

