# Echoman 启动指南

## 🚀 快速启动（推荐方式）

### 1. 启动后端（一键脚本）

在项目根目录运行：

```bash
./start.sh
```

效果：
- 启动 FastAPI（端口 **8778**）、Celery Worker、Celery Beat
- 自动 `docker-compose up -d postgres redis`（需已安装 docker-compose）
- 写日志到 `backend_services.log`，PID 保存在 `backend_services.pid`

如需停止所有后端服务：

```bash
./stop.sh
```

### 自由模式说明（必读）

自由模式需要先通过 **邀请码校验** 获取访问令牌：

- 接口：`POST /api/v1/free/verify`
- 成功后返回 `free_token`
- 调用 `POST /api/v1/chat/ask` 且 `mode=global` 时必须携带 `free_token`

令牌默认有效期 7 天，可在 `.env` 中配置：
- `FREE_MODE_INVITE_TTL_DAYS`
- `FREE_MODE_TOKEN_TTL_HOURS`

### 自定义启动组合

- 前台查看日志 / 精细控制：

```bash
python backend.py --all --db --restart-celery
```

其他示例：

```bash
python backend.py --api                 # 仅 API
python backend.py --worker              # 仅 Worker
python backend.py --beat                # 仅 Beat
python backend.py --api --worker        # API + Worker
python backend.py --all                 # API + Worker + Beat（不自动启 DB）
```

### 2. 启动前端

在新终端窗口运行：

```bash
python frontend.py
```

首次运行时会：
- 安装 npm 依赖
- 启动前端开发服务器（端口 5173）

### 3. 访问应用

- **前端界面**: http://localhost:5173
- **后端 API 文档**: http://localhost:8778/docs
- **健康检查**: http://localhost:8778/health

## 详细说明

### 后端启动流程

`backend.py` 脚本会按以下顺序执行：

1. **服务选择**
   - 通过命令行参数或交互式菜单选择要启动的服务
   - 支持启动 API、Worker、Beat 的任意组合

2. **检查数据库服务**
   - 检查 PostgreSQL (localhost:5432) 是否运行
   - 检查 Redis (localhost:6379) 是否运行
   - 如果未运行，提示使用 Docker 启动

3. **安装依赖**
   - 检查是否已安装 FastAPI、SQLAlchemy、Celery 等核心依赖
   - 推荐直接安装根目录 `requirements.txt`

4. **初始化数据库**
   - 创建 pgvector 扩展
   - 创建所有数据库表
   - 自动创建自由模式表与 `topic_item_mv` 物化视图（无需额外迁移脚本）
   - 显示已创建的表列表

5. **启动选定的服务**
   - **FastAPI 服务器**: 监听 0.0.0.0:8778，提供 API 接口
   - **Celery Worker**: 执行异步任务（如采集任务）
   - **Celery Beat**: 定时任务调度器，按时间表自动触发采集
   - 所有服务在同一终端运行，按 Ctrl+C 可一次性停止所有服务

### 前端启动流程

`frontend.py` 脚本会按以下顺序执行：

1. **检查依赖**
   - 检查 node_modules 是否存在
   - 如果不存在，自动执行 `npm install`

2. **启动开发服务器**
   - 运行 `npm run dev -- --host`
   - 允许局域网访问

## 环境要求

### 必需软件

- **Python 3.11+** 
- **Node.js 18+** (用于前端)
- **数据库**:
  -  Docker & Docker Compose - 快速开始，一键启动


## 数据库管理

### 使用 Docker

```bash
cd backend
docker-compose up -d postgres redis
```


### Chroma 向量数据库

系统使用 **Chroma** 作为主向量数据库，支持 4096 维向量（Qwen3-Embedding-8B）：

- **数据目录**: `backend/data/chroma/`
- **自动初始化**: 首次启动时自动创建
- **无需手动配置**: 开箱即用


## LLM 配置（必读）

后端会同时使用 **对话模型** 和 **Embedding 模型**。所有配置都写在 `.env`（可从 `env.template` 复制）。

核心变量：
- `LLM_PROVIDER`：`qwen` | `openai` | `azure` | `openai_compatible`
- `LLM_MAX_TOKENS` / `LLM_TEMPERATURE` / `LLM_TIMEOUT_SECONDS`：通用推理参数



说明：
- Embedding 可以单独配置地址与密钥：`OPENAI_COMPATIBLE_EMBEDDING_BASE_URL`、`OPENAI_COMPATIBLE_EMBEDDING_API_KEY`
- 若 Embedding 不配置，会复用对话模型的 base_url / api_key


### 使用 API 文档

访问 http://localhost:8778/docs 使用交互式 API 文档测试接口。

## 📊 后端服务说明

### 服务组件

| 组件 | 功能 | 必需 | 端口 |
|------|------|------|------|
| FastAPI | 提供 REST API 接口 | 是（前端通信） | 8778 |
| Celery Worker | 执行异步采集任务 | 否（手动触发采集需要） | - |
| Celery Beat | 定时任务调度器 | 否（自动采集需要） | - |
| PostgreSQL | 主数据库 | 是 | 5432 |
| Redis | 缓存和消息队列 | 是 | 6379 |

### 定时采集时间表

当启动 Celery Beat 后，系统会自动按以下时间表采集：

| 时间 | 任务 | 说明 |
|------|------|------|
| 08:00 | 采集任务 | 采集所有平台热榜 |
| 08:05 | MORN 归并 | 归并 08:00 数据 |
| 08:20 | MORN 整体归并 | 与历史话题比对 |
| 10:00 | 采集任务 | 采集所有平台热榜 |
| 12:00 | 采集任务 | 采集所有平台热榜 |
| 12:05 | AM 归并 | 归并 10:00/12:00 数据 |
| 12:20 | AM 整体归并 | 与历史话题比对 |
| 14:00 | 采集任务 | 采集所有平台热榜 |
| 16:00 | 采集任务 | 采集所有平台热榜 |
| 18:00 | 采集任务 | 采集所有平台热榜 |
| 18:05 | PM 归并 | 归并 14:00/16:00/18:00 数据 |
| 18:20 | PM 整体归并 | 与历史话题比对 |
| 20:00 | 采集任务 | 采集所有平台热榜 |
| 22:00 | 采集任务 | 采集所有平台热榜 |
| 22:05 | EVE 归并 | 归并 20:00/22:00 数据 |
| 22:20 | EVE 整体归并 | 与历史话题比对 |

**每次采集各平台热榜前 30 条数据**
