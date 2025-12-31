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
   - 如果未安装，自动执行 `pip install -r requirements.txt`

4. **初始化数据库**
   - 创建 pgvector 扩展
   - 创建所有数据库表
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

- **Python 3.11+** (通过 conda echoman 环境)
- **Node.js 18+** (用于前端)
- **数据库（二选一）**:
  - **选项1 (推荐)**: Docker & Docker Compose - 快速开始，一键启动
  - **选项2**: 本地安装 PostgreSQL 15+ 和 Redis 6+ - 完全控制，适合生产环境
  - 详见: [本地数据库安装指南](./backend/INSTALL_LOCAL_DATABASE.md)

### Conda 环境

确保已创建并激活 `echoman` 环境：

```bash
conda create -n echoman python=3.11
conda activate echoman
```

## 数据库管理

### 📚 数据库安装文档导航

- 🆚 [对比两种方式](./backend/DATABASE_OPTIONS.md) - 帮助您选择
- 📝 [快速安装摘要](./backend/DATABASE_SETUP_SUMMARY.md) - 一键安装命令
- 📖 [本地安装详细教程](./backend/INSTALL_LOCAL_DATABASE.md) - 完整步骤

### 方式一：使用 Docker（推荐新手）

```bash
cd backend
docker-compose up -d postgres redis
```

### 方式二：本地安装（推荐生产）

查看 [INSTALL_LOCAL_DATABASE.md](./backend/INSTALL_LOCAL_DATABASE.md)

### 手动管理数据库表

```bash
cd backend

# 创建表
python scripts/init_tables.py create

# 删除表（危险操作）
python scripts/init_tables.py drop

# 重新创建表
python scripts/init_tables.py recreate
```

### Chroma 向量数据库

系统使用 **Chroma** 作为主向量数据库，支持 4096 维向量（Qwen3-Embedding-8B）：

- **数据目录**: `backend/data/chroma/`
- **自动初始化**: 首次启动时自动创建
- **无需手动配置**: 开箱即用

📖 **详细文档**: [Chroma 向量数据库配置](./docs/CHROMA_VECTOR_DATABASE.md)

### 查看数据库

```bash
# 连接 PostgreSQL
psql -h localhost -U echoman -d echoman

# 常用命令
\dt                    # 查看所有表
\d source_items        # 查看表结构
SELECT * FROM topics;  # 查询数据
\q                     # 退出
```

## 测试 API（端口 8778）

### 使用 curl

```bash
# 健康检查
curl http://localhost:8778/health

# 触发采集
curl -X POST "http://localhost:8778/api/v1/ingest/run" \
  -H "Content-Type: application/json" \
  -d '{"platforms": ["weibo", "zhihu"], "limit": 10}'

# 查看采集历史
curl http://localhost:8778/api/v1/ingest/runs

# 查看话题列表
curl "http://localhost:8778/api/v1/topics?page=1&size=20"
```

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
| 10:00 | 采集任务 | 采集所有平台热榜 |
| 12:00 | 采集任务 | 采集所有平台热榜 |
| 12:15 | 上半日归并 | 归并上午数据 |
| 12:30 | 整体归并 | 全局归并 |
| 14:00 | 采集任务 | 采集所有平台热榜 |
| 16:00 | 采集任务 | 采集所有平台热榜 |
| 18:00 | 采集任务 | 采集所有平台热榜 |
| 20:00 | 采集任务 | 采集所有平台热榜 |
| 22:00 | 采集任务 | 采集所有平台热榜 |
| 22:15 | 下半日归并 | 归并下午数据 |
| 22:30 | 整体归并 | 全局归并 |

**每次采集各平台热榜前 30 条数据**

### 高级功能

#### 监控 Celery 任务（可选）

启动 Flower 监控界面：

```bash
cd backend
conda activate echoman
celery -A app.tasks.celery_app flower --port=5555
```

访问 http://localhost:5555 查看任务监控界面。

#### 分离运行服务（不推荐，除非特殊需求）

如果需要在不同终端分别运行各服务：

```bash
# 终端 1: API 服务器
python backend.py --api

# 终端 2: Celery Worker
python backend.py --worker

# 终端 3: Celery Beat
python backend.py --beat
```

## 常见问题

### Q1: 端口被占用

**问题**: `Address already in use` 错误

**解决**:
```bash
# 查找占用端口的进程
lsof -i :8778
lsof -i :5173

# 杀死进程
kill -9 <PID>
```

### Q2: 数据库连接失败

**问题**: 无法连接到 PostgreSQL

**解决**:
```bash
# 检查 Docker 容器状态
cd backend
docker-compose ps

# 查看日志
docker-compose logs postgres

# 重启数据库
docker-compose restart postgres
```

### Q3: 依赖安装失败

**问题**: pip install 出错

**解决**:
```bash
# 升级 pip
pip install --upgrade pip

# 清理缓存并重新安装
pip cache purge
pip install -r backend/requirements.txt
```

### Q4: 前端启动失败

**问题**: npm 相关错误

**解决**:
```bash
cd frontend

# 删除依赖并重新安装
rm -rf node_modules package-lock.json
npm install

# 清理缓存
npm cache clean --force
```

## 🛑 停止服务

### 停止后端

在后端运行窗口按 `Ctrl+C`

**新版 backend.py 会自动优雅停止所有服务（API、Worker、Beat）**

### 停止前端

在前端运行窗口按 `Ctrl+C`

### 停止数据库

```bash
cd backend
docker-compose down

# 或者只停止服务，保留数据
docker-compose stop
```

## 目录结构

```
Echoman/
├── backend.py              # 后端启动脚本 ✨
├── frontend.py             # 前端启动脚本 ✨
├── backend/                # 后端代码
│   ├── app/               # FastAPI 应用
│   ├── scrapers/          # 爬虫模块
│   ├── scripts/           # 工具脚本
│   ├── requirements.txt   # Python 依赖
│   ├── docker-compose.yml # Docker 配置
│   ├── backend_quickstart.md     # 详细启动指南
│   └── PROJECT_STATUS.md # 项目状态
├── frontend/              # 前端代码
├── docs/                  # 文档
└── HOW_TO_START.md       # 本文档
```

## 下一步

1. 访问前端界面开始使用
2. 查看 API 文档了解接口
3. 测试采集功能
4. 查看项目状态了解待实现功能

## 相关文档

- [后端快速启动](./backend/backend_quickstart.md) - 详细的后端启动说明
- [后端完整文档](./backend/BACKEND_README.md) - 后端架构和功能说明
- [项目状态](./backend/PROJECT_STATUS.md) - 当前实现进度
- [API 规范](./docs/api-spec.md) - API 接口文档
- [方案设计](./docs/backend-solution.md) - 系统设计方案

---

**提示**: 首次启动可能需要几分钟时间下载依赖和初始化数据库，请耐心等待。
