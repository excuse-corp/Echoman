# Echoman - 热点事件聚合与回声追踪系统

> 一个智能的多平台热点事件聚合系统，追踪事件的传播和演化轨迹

## 🎯 项目简介

Echoman 是一个热点事件聚合与回声追踪系统，通过采集多个平台的热点数据，进行智能归并和分析，追踪事件的传播和演化轨迹。

### 核心特性

- **多平台采集**: 微博、知乎、今日头条、新浪新闻、网易新闻、百度热搜、虎扑
- **智能归并**: 两层归并机制（半日归并 + 整体归并）
- **热度追踪**: 归一化热度计算，追踪事件热度变化
- **回声指标**: 强度（Intensity）、长度（Length）、热度趋势
- **LLM 驱动**: 使用 Qwen3-32B 进行事件关联判定
- **RAG 对话**: 基于检索增强的事件问答系统（双模式：事件模式/自由模式）
- **现代化UI**: 玻璃拟态设计、完整暗色/亮色主题、流畅动画效果
- **智能交互**: SSE流式对话、自动刷新、Enter发送、时间线紧凑展示

## 🚀 快速启动

### 前置要求

- Python 3.11+ (conda echoman 环境)
- Node.js 18+
- **数据库（二选一）**:
  - 选项1: Docker & Docker Compose（快速开始）
  - 选项2: 本地 PostgreSQL 15+ 和 Redis 6+（完全控制）
  - 📖 [如何选择？查看对比](./backend/DATABASE_OPTIONS.md)
  - 📖 [本地数据库安装指南](./backend/INSTALL_LOCAL_DATABASE.md)

### 一键启动

#### 1. 启动后端

```bash
# 在项目根目录运行
python backend.py
```

首次运行会自动：
- 启动 PostgreSQL 和 Redis（使用 Docker）
- 安装 Python 依赖
- 初始化数据库表结构
- 启动 FastAPI 服务器（端口 8000）

#### 2. 启动前端

```bash
# 在新终端窗口运行
python frontend.py
```

首次运行会自动：
- 安装 npm 依赖
- 启动开发服务器（端口 5173）

### 访问应用

- **前端界面**: http://localhost:5173
- **后端 API**: http://localhost:8000/docs
- **健康检查**: http://localhost:8000/health

## 📚 文档导航

- **[快速启动指南](./HOW_TO_START.md)** - 完整的启动步骤和常见问题
- **[后端快速启动](./backend/backend_quickstart.md)** - 后端详细启动说明
- **[后端完整文档](./backend/BACKEND_README.md)** - 后端架构和功能说明
- **[项目状态](./backend/PROJECT_STATUS.md)** - 当前实现进度和待办事项
- **[API 规范](./docs/api-spec.md)** - API 接口文档
- **[方案设计](./docs/backend-solution.md)** - 系统设计方案

## 📊 项目状态

### ✅ 项目整体进度（90%）🚀
**核心后端功能已100%完成，前端核心页面已完成（85%）**

**阶段1: 数据获取与存储** - 已完成！✅

- [x] 完整的项目架构
- [x] 7个平台爬虫集成
- [x] 数据库模型设计与实现（10个核心表）
- [x] FastAPI 完整接口
- [x] 采集服务与运行追踪
- [x] **热度归一化服务**（Min-Max + 平台权重）✨
- [x] **半日归并逻辑**（向量聚类 + LLM判定）✨
- [x] **整体归并逻辑**（Topic创建与归并）✨
- [x] **LLM Provider 抽象层**（Qwen/OpenAI/Azure）✨
- [x] **完整的Celery任务调度**（采集+归并）✨
- [x] Docker 部署配置
- [x] 源码启动脚本（backend.py）
- [x] 完整文档体系

**阶段2: AI 处理** - 已完成！✅

- [x] LLM Provider 集成（Qwen/OpenAI/Azure）✨
- [x] 向量检索服务（pgvector + embedding）✨
- [x] 事件归并判定（LLM智能判定）✨
- [x] **事件分类服务（三分类：娱乐/时事/体育）**✨
- [x] **摘要生成服务（增量摘要）**✨
- [x] **RAG 对话系统（topic/global模式）**✨

### ✅ 增强功能（已完成）

- [x] **RAG 对话系统（topic模式 + global模式）**✨
- [x] **事件自动分类（娱乐/时事/体育三分类）**✨
- [x] **增量摘要生成**✨
- [x] **Chroma 向量数据库（支持 4096 维向量，突破 pgvector 维度限制）**✨
- [x] **向量检索优化（Chroma HNSW 索引 + 高维向量支持）**✨
- [x] **监控与告警系统（Prometheus + Grafana）**✨

📖 **详细进度**: 查看 [实现完成报告](./backend/IMPLEMENTATION_COMPLETE.md)

## 🛠️ 技术栈

### 后端

- **框架**: FastAPI + uvicorn
- **数据库**: PostgreSQL 15 + pgvector
- **向量数据库**: Chroma 1.3.0（支持 4096 维向量，无维度限制）
- **缓存**: Redis 6
- **任务队列**: Celery + Beat
- **ORM**: SQLAlchemy (async)
- **爬虫**: httpx + BeautifulSoup4
- **AI**: LangChain (已集成) + OpenAI SDK (Qwen/OpenAI/Azure)
- **Embedding**: 支持 Qwen3-Embedding-8B (4096维) / text-embedding-3-large 等高维模型

### 前端

- **框架**: React 18.3 + Vite 5.2 + TypeScript 5.5
- **路由**: React Router v6.26
- **UI**: 零依赖原生CSS实现（轻量级）
- **设计系统**: 玻璃拟态（Glassmorphism）+ 现代渐变
- **主题**: 完整的暗色/亮色模式系统
- **交互**: SSE流式对话 + 自动滚动 + Enter发送
- **开发状态**: 核心页面和组件已完成（85%）✨
- **特色**: Fallback机制 + 优雅降级 + 紧凑优化设计

## 📦 项目结构

```
Echoman/
├── backend.py              # 后端启动脚本 ✨
├── frontend.py             # 前端启动脚本 ✨
├── HOW_TO_START.md        # 启动指南 ✨
├── backend/               # 后端代码
│   ├── app/              # FastAPI 应用
│   │   ├── api/         # API 路由
│   │   ├── models/      # 数据库模型
│   │   ├── services/    # 业务逻辑
│   │   ├── tasks/       # Celery 任务
│   │   ├── schemas/     # Pydantic 模型
│   │   ├── config/      # 配置管理
│   │   └── main.py      # 应用入口
│   ├── scrapers/        # 爬虫模块
│   ├── scripts/         # 工具脚本
│   ├── requirements.txt # Python 依赖
│   └── docker-compose.yml
├── frontend/            # 前端代码
└── docs/               # 文档
    ├── api-spec.md           # API 规范
    └── backend-solution.md   # 方案设计
```

## 🧪 测试 API

### 使用 curl

```bash
# 触发采集
curl -X POST "http://localhost:8000/api/v1/ingest/run" \
  -H "Content-Type: application/json" \
  -d '{"platforms": ["weibo", "zhihu"], "limit": 10}'

# 查看采集历史
curl "http://localhost:8000/api/v1/ingest/runs"

# 查看话题列表
curl "http://localhost:8000/api/v1/topics?page=1&size=20"

# 查看平台状态
curl "http://localhost:8000/api/v1/ingest/sources/status"
```

### 使用 API 文档

访问 http://localhost:8000/docs 使用交互式 API 文档。

## 🔧 高级功能

### 启动 Celery Worker（定时任务）

```bash
cd backend
conda activate echoman
celery -A app.tasks.celery_app worker --loglevel=info
```

### 启动 Celery Beat（任务调度）

```bash
cd backend
conda activate echoman
celery -A app.tasks.celery_app beat --loglevel=info
```

### 监控 Celery 任务

```bash
cd backend
conda activate echoman
celery -A app.tasks.celery_app flower --port=5555
```

访问 http://localhost:5555

## 📈 开发路线图

### 阶段 1: 数据获取与存储（100% 完成）✅

- [x] 多平台爬虫集成（7个平台）
- [x] 数据库模型设计（10个核心表）
- [x] 采集服务实现（Celery定时任务）
- [x] 基础 API 接口（FastAPI REST）
- [x] 热度归一化（Min-Max + 平台权重）
- [x] 归并逻辑（半日归并 + 整体归并）

### 阶段 2: AI 处理与对话（100% 完成）✅

- [x] LLM Provider 集成（Qwen/OpenAI/Azure）
- [x] 向量检索服务（pgvector + embedding）
- [x] 事件归并判定（向量聚类 + LLM判定）
- [x] **事件分类（娱乐/时事/体育三分类）**✨
- [x] **摘要生成（增量摘要生成）**✨
- [x] **RAG 对话系统（topic/global模式）**✨

### 阶段 3: 前端与可视化（85% 完成）🚧

- [x] 基础页面结构（首页 + 探索页）✨
- [x] 品牌首页完整实现（回声指标+分类统计）✨
- [x] 事件列表与详情展示✨
- [x] 时间线展示组件（紧凑优化设计）✨
- [x] AI对话界面（ConversationConsole双模式）✨
- [x] 智能对话系统（SSE流式响应 + 自动滚动）✨
- [x] 对话交互优化（Enter发送、刷新重置、事件模式专注）✨
- [x] 主题切换（完整的暗色/亮色模式系统）✨
- [x] UI/UX全面优化（玻璃拟态、紧凑布局、视觉统一）✨
- [x] API服务封装（含Fallback机制）✨
- [x] 零UI库依赖（原生CSS实现）✨
- [ ] 后端API集成完善（当前使用Fallback数据）
- [ ] 图表可视化（Recharts/ECharts集成）
- [ ] 响应式设计增强
- [ ] 管理后台界面

## 🤝 贡献指南

欢迎提交 Issue 和 Pull Request！

## 📄 许可证

MIT License

## 📧 联系方式

如有问题或建议，请提交 Issue。

---

**提示**: 首次启动可能需要几分钟时间下载依赖和初始化数据库，请耐心等待。

**开始使用**: 运行 `python backend.py` 和 `python frontend.py` 即可启动整个系统！

