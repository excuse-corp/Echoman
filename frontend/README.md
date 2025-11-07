# Echoman Frontend - 热点追踪前端系统

## 项目概述

Echoman前端系统是一个基于React + TypeScript的现代化Web应用，用于展示和分析多平台热点数据。系统提供热点主题列表、详情、时间线展示、分类统计和AI对话等功能。

## 技术栈

### ✅ 当前使用的技术栈

#### 核心框架
- **React 18.3.1**: 构建用户界面
- **TypeScript 5.5.4**: 类型安全的JavaScript超集
- **Vite 5.2.0**: 快速的构建工具和开发服务器
- **React Router v6.26.2**: 客户端路由管理

#### UI实现
- **原生CSS**: 自定义样式系统，无外部UI库依赖
- **主题系统**: 完整的暗色/亮色主题切换实现
- **响应式设计**: 适配桌面和移动端（基础支持）


### 🎨 设计特点

- **轻量级**: 零UI组件库依赖，包体积小
- **高性能**: Vite构建，热更新快速
- **优雅降级**: API失败时自动使用Fallback数据
- **暗色模式**: 完整的主题切换支持

## 项目结构

```
frontend/
├── src/
│   ├── components/           # 可复用组件
│   │   ├── ConversationConsole.tsx  # AI对话控制台
│   │   ├── Timeline.tsx             # 时间线组件
│   │   ├── ThemeToggle.tsx          # 主题切换按钮
│   │   └── icons/                   # 图标组件
│   ├── pages/               # 页面组件
│   │   ├── HomePage.tsx       # 首页（品牌介绍+分类统计）
│   │   └── ExplorerPage.tsx   # 探索页（热点列表+详情+对话）
│   ├── services/            # API服务
│   │   └── api.ts            # API封装（含Fallback数据）
│   ├── types.ts            # TypeScript类型定义
│   ├── theme.tsx           # 主题系统实现
│   ├── styles.css          # 全局样式
│   ├── App.tsx             # 应用主组件（路由配置）
│   └── main.tsx            # 应用入口
├── public/                 # 静态资源
├── index.html             # HTML模板
├── package.json           # 项目依赖
├── tsconfig.json          # TypeScript配置
├── vite.config.ts         # Vite配置
└── README.md             # 本文件
```

## 快速开始

### 方式一：使用启动脚本（推荐）

```bash
# 在项目根目录运行
python frontend.py
```

首次运行会自动：
- 安装 npm 依赖
- 启动开发服务器

### 方式二：手动启动

```bash
# 1. 安装依赖
cd frontend
npm install

# 2. 启动开发服务器
npm run dev
```

### 访问应用

- **前端界面**: http://localhost:5173
- **首页**: http://localhost:5173/
- **探索页**: http://localhost:5173/explore

### 构建生产版本

```bash
cd frontend
npm run build
```

构建产物将输出到 `dist/` 目录

## 核心功能模块

### 1. 首页（HomePage）

**路径**: `/`

**功能特性**:
- **品牌介绍区**:
  - Logo和Slogan展示
  - 项目介绍和核心价值传递
  - "一探究竟"CTA按钮（跳转至探索页）
- **回声指标展示**:
  - 回声强度：覆盖总量
  - 回声时长：回声持续时间
  - 回声热度：从多平台累计热度
- **分类统计卡片**:
  - 三大分类：娱乐八卦、社会实事、体育电竞
  - 每类显示：平均时长、最长时长、最短时长
- **数据源标识**:
  - 显示7个数据源平台（微博、知乎、今日头条、新浪新闻、网易新闻、百度热搜、虎扑）

**API调用**:
```typescript
GET ${API_BASE_URL}/api/v1/categories/metrics/summary
```

**关键组件**:
- 品牌展示区（hero section）
- 回声指标卡片
- 分类统计卡片（3个）
- 主题切换按钮（ThemeToggle）

### 2. 探索页（ExplorerPage）

**路径**: `/explore`

**功能特性**:
- **左侧：热点列表**:
  - 显示所有热点主题
  - 每个热点卡片显示：标题、摘要、强度、时长、状态、平台分布
  - 支持点击查看详情
  - 列表自动滚动
- **右侧：详情+对话面板**:
  - **主题详情区**（选中热点时显示）:
    - 标题和摘要
    - 关键要点列表
    - 实体信息（人物、组织、地点）
  - **事件时间线**:
    - 按时间倒序展示所有节点
    - 每个节点显示：时间、标题、内容、平台、互动数
    - Timeline组件展示
  - **AI对话区**（ConversationConsole）:
    - 两种模式：自由对话（free）/ 事件对话（event）
    - 支持流式输出（模拟）
    - 消息历史展示
    - 输入框和发送按钮

**API调用**:
```typescript
GET ${API_BASE_URL}/api/v1/topics
GET ${API_BASE_URL}/api/v1/topics/:id
GET ${API_BASE_URL}/api/v1/topics/:id/timeline
```

**关键组件**:
- 热点列表（左侧面板）
- 详情展示区（右上）
- Timeline组件（右中）
- ConversationConsole组件（右下）
- ThemeToggle按钮

### 3. 核心组件说明

#### ConversationConsole (AI对话控制台)

**功能特性**:
- 支持两种模式：
  - `free`: 自由对话模式
  - `event`: 基于选定主题的对话模式
- 消息历史展示
- **流式输出** ⚡️:
  - 当前: 模拟流式输出（前端实现）
  - 计划: SSE真实流式输出（等待后端API）
  - 事件类型: `token`, `citations`, `done`
- 模式切换按钮
- 输入框和发送功能

**使用位置**: ExplorerPage

**待实现**:
- [ ] 集成SSE流式对话API
- [ ] 使用 EventSource 接收实时token
- [ ] 显示引用来源和诊断信息

#### Timeline (时间线组件)

**功能特性**:
- 展示事件的时间线节点
- 每个节点显示：时间、标题、内容、平台、互动数
- 支持平台图标显示
- 时间格式化显示

**使用位置**: ExplorerPage

#### ThemeToggle (主题切换)

**功能特性**:
- 暗色/亮色主题切换
- 状态持久化（localStorage）
- 流畅的过渡动画
- 图标切换提示

**使用位置**: HomePage, ExplorerPage

## TypeScript类型定义

### 核心类型（types.ts）

```typescript
/**
 * 热点摘要
 */
export interface HotspotSummary {
  topic_id: string;
  title: string;
  summary: string;
  intensity_raw: number;
  intensity_norm: number;
  length_days: number;
  first_seen: string;
  last_active: string;
  platforms: string[];
  platform_mentions: Record<string, number>;
  status: "active" | "ended";
}

/**
 * 分类统计
 */
export interface CategoryEchoStat {
  category: string;
  average_hours: number;
  longest_hours: number;
  shortest_hours: number;
}

/**
 * 主题详情
 */
export interface TopicDetail {
  topic: HotspotSummary;
  key_points: string[];
  entities: {
    persons?: string[];
    organizations?: string[];
    locations?: string[];
  };
}

/**
 * 时间线节点
 */
export interface TimelineNode {
  node_id: string;
  topic_id: string;
  timestamp: string;
  title: string;
  content: string;
  source_platform: string;
  source_url: string;
  captured_at: string;
  engagement: number;
}
```

## 样式与主题

### 主题系统（theme.tsx）

```typescript
// 主题系统实现
export function ThemeProvider({ children }: { children: React.ReactNode }) {
  const [theme, setTheme] = useState<"light" | "dark">(() => {
    const saved = localStorage.getItem("theme");
    return (saved === "dark" ? "dark" : "light");
  });

  useEffect(() => {
    document.documentElement.setAttribute("data-theme", theme);
    localStorage.setItem("theme", theme);
  }, [theme]);

  const toggleTheme = () => {
    setTheme(prev => prev === "light" ? "dark" : "light");
  };

  return (
    <ThemeContext.Provider value={{ theme, toggleTheme }}>
      {children}
    </ThemeContext.Provider>
  );
}
```

### CSS变量系统（styles.css）

```css
/* 亮色主题 */
[data-theme="light"] {
  --bg-primary: #ffffff;
  --bg-secondary: #f5f7fa;
  --text-primary: #1a1a1a;
  --text-secondary: #666666;
  --border-color: #e0e0e0;
  --accent-color: #0066ff;
}

/* 暗色主题 */
[data-theme="dark"] {
  --bg-primary: #1a1a1a;
  --bg-secondary: #2d2d2d;
  --text-primary: #ffffff;
  --text-secondary: #b0b0b0;
  --border-color: #404040;
  --accent-color: #4a9eff;
}
```

### 响应式设计

- 桌面端：完整布局（左右分栏）
- 移动端：基础适配（单栏布局）
- 断点：768px

## API集成

### API封装（services/api.ts）

```typescript
// API基础URL，后端使用 /api/v1 前缀
const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000/api/v1";

// 1. 获取热点列表
export async function getHotspots(): Promise<{ items: HotspotSummary[]; fallback: boolean }> {
  try {
    // 后端API路径: GET /api/v1/topics
    const response = await fetch(`${API_BASE_URL}/topics`);
    if (!response.ok) throw new Error(`Bad status: ${response.status}`);
    const payload = await response.json();
    return { items: payload.items, fallback: false };
  } catch (error) {
    // 失败时返回Fallback数据
    return { items: fallbackHotspots, fallback: true };
  }
}

// 2. 获取分类统计
export async function getCategoryEchoStats(): Promise<{ items: CategoryEchoStat[]; fallback: boolean }> {
  try {
    // 后端API路径: GET /api/v1/categories/metrics/summary
    const response = await fetch(`${API_BASE_URL}/categories/metrics/summary`);
    if (!response.ok) throw new Error(`Bad status: ${response.status}`);
    const payload = await response.json();
    return { items: payload.items, fallback: false };
  } catch (error) {
    return { items: fallbackCategoryStats, fallback: true };
  }
}

// 3. 获取主题详情
export async function getTopicDetail(topicId: string): Promise<{ detail: TopicDetail | null; fallback: boolean }> {
  try {
    // 后端API路径: GET /api/v1/topics/{topic_id}
    const response = await fetch(`${API_BASE_URL}/topics/${topicId}`);
    if (!response.ok) throw new Error(`Bad status: ${response.status}`);
    const payload = await response.json();
    return { detail: payload, fallback: false };
  } catch (error) {
    return { detail: fallbackDetails[topicId] ?? null, fallback: true };
  }
}

// 4. 获取时间线
export async function getTimeline(topicId: string): Promise<{ nodes: TimelineNode[]; fallback: boolean }> {
  try {
    // 后端API路径: GET /api/v1/topics/{topic_id}/timeline
    // 返回分页数据，需要提取items字段
    const response = await fetch(`${API_BASE_URL}/topics/${topicId}/timeline`);
    if (!response.ok) throw new Error(`Bad status: ${response.status}`);
    const payload = await response.json();
    // 后端返回 {page, size, total, items}，需要提取items
    const nodes = payload.items || payload.nodes || [];
    return { nodes, fallback: false };
  } catch (error) {
    return { nodes: fallbackTimelines[topicId] ?? [], fallback: true };
  }
}
```

### Fallback机制

所有API调用都内置了Fallback机制：
- API请求失败时自动返回预定义的Mock数据
- 用户界面不会因为API故障而崩溃
- 开发阶段无需后端即可预览界面效果

## 性能优化

### 当前实现的优化

1. **轻量级依赖**
   - 无UI组件库，减少bundle大小
   - 仅3个核心依赖（React, React-DOM, React-Router）
   - 生产构建体积小

2. **主题持久化**
   - localStorage缓存用户主题选择
   - 避免每次加载时的闪烁

3. **请求取消**
   - useEffect清理函数处理组件卸载
   - 避免状态更新警告

4. **优雅降级**
   - Fallback数据机制
   - API失败不影响用户体验

### 未来优化方向

1. **代码分割**
   - React.lazy懒加载路由页面
   - 动态导入大型组件

2. **缓存策略**
   - 添加SWR或React Query
   - 实现请求去重和缓存复用

3. **虚拟滚动**
   - 长列表性能优化
   - react-window集成

## 开发规范

### 组件编写规范
- 使用函数式组件 + Hooks
- Props类型必须明确定义
- 复杂逻辑抽离为自定义Hook
- 使用memo优化不必要的重渲染

### 命名规范
- 组件：PascalCase（如 TopicCard）
- 函数/变量：camelCase（如 fetchTopics）
- 常量：UPPER_SNAKE_CASE（如 API_BASE_URL）
- 类型/接口：PascalCase（如 Topic, TopicStatus）

### 文件组织
- 一个文件一个组件（除非紧密相关）
- 样式可选：CSS Modules / styled-components / MUI sx prop
- 测试文件与组件同目录：ComponentName.test.tsx

## 后端API对接状态

### ✅ 已对接的API（4个）

1. **热点列表**: `GET /api/v1/topics`
   - 前端函数: `getHotspots()`
   - 用于: 探索页热点列表
   - 状态: ✅ 已完成

2. **分类统计**: `GET /api/v1/categories/metrics/summary`
   - 前端函数: `getCategoryEchoStats()`
   - 用于: 首页分类统计卡片
   - 状态: ✅ 已完成

3. **主题详情**: `GET /api/v1/topics/{id}`
   - 前端函数: `getTopicDetail(topicId)`
   - 用于: 探索页主题详情展示
   - 状态: ✅ 已完成

4. **时间线**: `GET /api/v1/topics/{id}/timeline`
   - 前端函数: `getTimeline(topicId)`
   - 用于: 探索页事件时间线
   - 状态: ✅ 已完成

### ✅ 新完成的API（1个）

5. **SSE流式对话**: `POST /api/v1/chat/ask` (stream=true) ⚡️
   - 前端集成代码: `frontend/src/services/sse.ts`
   - 使用示例:
     ```typescript
     import { startSSEStream } from './services/sse';
     
     const cleanup = await startSSEStream({
       query: "最近有什么热点新闻？",
       mode: "global",
       onToken: (content) => {
         // 逐字显示内容
       },
       onCitations: (citations) => {
         // 显示引用来源
       },
       onDone: (diagnostics) => {
         // 显示诊断信息
       },
       onError: (message) => {
         // 错误处理
       },
     });
     ```
   - 用于: ConversationConsole组件的实时流式输出
   - 状态: ✅ 已完成并测试通过
   - 文档: [SSE集成指南](../docs/sse-integration-guide.md)

### 📝 API路径说明

- **Base URL**: 通过环境变量 `VITE_API_BASE_URL` 配置
- **默认值**: `http://localhost:8000/api/v1`
- **注意**: 后端使用 `/api/v1` 作为API前缀

### 🔧 环境配置

创建 `.env.development` 或 `.env.production`：

```env
# 开发环境
VITE_API_BASE_URL=http://localhost:8000/api/v1

# 生产环境
VITE_API_BASE_URL=https://api.echoman.com/api/v1
```

### ⚠️ 数据源说明

当前支持的7个平台：
1. 微博 (weibo)
2. 知乎 (zhihu)
3. 今日头条 (toutiao)
4. 新浪新闻 (sina)
5. 网易新闻 (netease)
6. 百度热搜 (baidu)
7. 虎扑 (hupu)

**已移除的平台**（因技术难度或API不稳定）：
- ❌ 抖音 (douyin)
- ❌ 小红书 (xhs)
- ❌ 腾讯新闻 (tencent)

## 部署

### 环境变量

创建 `.env.production`：

```env
# 生产环境API地址（注意包含/api/v1前缀）
VITE_API_BASE_URL=https://api.echoman.com/api/v1
VITE_SSE_URL=https://api.echoman.com/api/v1/chat/stream
```

### 构建与部署

```bash
# 构建
npm run build

# 预览构建产物
npm run preview

# 部署到Nginx
cp -r dist/* /var/www/echoman/
```

### Nginx配置示例

```nginx
server {
    listen 80;
    server_name echoman.com;
    root /var/www/echoman;
    index index.html;

    location / {
        try_files $uri $uri/ /index.html;
    }

    location /api/ {
        proxy_pass http://localhost:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

## 实现状态

### ✅ 已完成功能（75%）

#### 页面（2/2）
- [x] **HomePage**: 品牌首页
  - 完整的品牌展示
  - 回声指标说明
  - 分类统计卡片
  - 主题切换支持
- [x] **ExplorerPage**: 热点探索页
  - 热点列表展示
  - 主题详情面板
  - 事件时间线
  - AI对话集成

#### 核心组件（3/3）
- [x] **ConversationConsole**
  - 双模式对话（free/event）
  - 消息历史
  - 流式输出模拟
- [x] **Timeline**
  - 时间线节点展示
  - 平台图标
  - 时间格式化
- [x] **ThemeToggle**
  - 暗色/亮色主题切换
  - 状态持久化

#### 功能特性
- [x] Fallback数据机制
- [x] 主题系统（完整实现）
- [x] 响应式设计（基础）
- [x] API封装
- [x] 路由系统

### 🚧 待完善功能

#### 高优先级（P0）
- [x] **SSE流式对话** ⚡️ ✅ **已完成**
  - 后端API：`POST /api/v1/chat/ask` (stream=true) ✅
  - 前端集成：`frontend/src/services/sse.ts` ✅
  - 事件类型：`token`, `citations`, `done`, `error` ✅
  - 测试状态：通过 ✅
  - 文档：[SSE集成指南](../docs/sse-integration-guide.md) ✅
  
- [ ] **ConversationConsole组件集成SSE**
  - 将模拟流式输出替换为真实SSE流式
  - 使用 `startSSEStream` 函数
  - 实现加载状态和错误处理
  
- [x] **后端API集成完善**
  - ✅ API路径已修正（/api/v1前缀）
  - ✅ 核心5个API已对接（包括SSE流式对话）
  - ✅ 所有接口已验证正常工作

#### 中优先级（P1）
- [ ] **图表可视化**
  - 集成Recharts或ECharts
  - 实现分类趋势图
  - ~~热度趋势图~~（已确认不需要）

- [ ] **响应式设计增强**
  - 移动端布局优化
  - 触摸交互优化
  
- [ ] **列表筛选和排序**
  - 热点列表筛选功能
  - 多维度排序

#### 低优先级（P2）
- [ ] **高级功能**
  - 国际化（i18n）
  - PWA支持
  - ~~WebSocket实时通知~~（暂不需要）

#### ❌ 已确认不需要的功能
- ~~管理后台~~ - 暂不实现
- ~~系统监控界面~~ - 暂不实现
- ~~热度趋势图~~ - 前端无需求

## 技术文档

- [backend-solution.md](../docs/backend-solution.md): 后端方案设计
- [api-spec.md](../docs/api-spec.md): API接口文档
- [merge-logic.md](../docs/merge-logic.md): 归并逻辑说明

## 项目亮点

### 1. 零UI库依赖
- 完全自定义的CSS实现
- 更小的包体积
- 更高的性能

### 2. 完整的Fallback机制
- API失败时自动降级到Mock数据
- 开发阶段无需后端即可运行
- 用户体验不受API影响

### 3. 优雅的暗色模式
- 完整的主题系统
- CSS变量实现
- 状态持久化

### 4. TypeScript全面覆盖
- 完整的类型定义
- 更好的开发体验
- 更少的运行时错误

## 开发建议

1. **先启动后端**
   - 运行 `python backend.py`
   - 确保API服务可用

2. **再启动前端**
   - 运行 `python frontend.py`
   - 访问 http://localhost:5173

3. **API调试**
   - 后端API文档: http://localhost:8000/docs
   - 后端健康检查: http://localhost:8000/health
   - 前端会自动尝试连接后端（Base URL: http://localhost:8000/api/v1）

4. **Fallback数据**
   - API失败时会自动使用Mock数据
   - 可在开发者工具中查看console警告

## 联系方式

如有问题或建议，请提交Issue或Pull Request。

