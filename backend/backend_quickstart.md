# Echoman 后端快速启动指南（源码方式）

## 🚀 快速启动（推荐方式）

### 1. 使用 backend.py 启动脚本（一键启动所有服务）

在项目根目录运行：

```bash
# 方式一：启动所有服务（推荐）
python backend.py --all

# 方式二：交互式选择服务
python backend.py

# 方式三：仅启动 API 服务器
python backend.py --api
```

**启动所有服务后，该脚本会自动完成：**
- ✅ 检查 PostgreSQL 和 Redis 是否运行
- ✅ 自动安装 Python 依赖（如果需要）
- ✅ 初始化数据库表结构
- ✅ 启动 FastAPI 服务器（端口 8000）
- ✅ 启动 Celery Worker（执行异步任务）
- ✅ 启动 Celery Beat（定时任务调度）

**所有服务在一个终端运行，按 Ctrl+C 可一次性停止所有服务。**

### 2. 访问服务

启动成功后，可以访问：

- **API 文档 (Swagger)**: http://localhost:8000/docs
- **API 文档 (ReDoc)**: http://localhost:8000/redoc
- **健康检查**: http://localhost:8000/health

### 3. 测试采集接口

```bash
# 手动触发采集（微博 + 知乎）
curl -X POST "http://localhost:8000/api/v1/ingest/run" \
  -H "Content-Type: application/json" \
  -d '{"platforms": ["weibo", "zhihu"], "limit": 10}'

# 查看采集历史
curl "http://localhost:8000/api/v1/ingest/runs?limit=10"

# 查看话题列表
curl "http://localhost:8000/api/v1/topics?page=1&size=20"

# 查看平台状态
curl "http://localhost:8000/api/v1/ingest/sources/status"
```

## 📋 详细步骤说明

### 步骤 1: 环境准备

#### 1.1 确保 conda echoman 环境已激活

```bash
conda activate echoman
```

#### 1.2 启动数据库服务

您可以选择以下任一方式启动数据库：

**方式一：使用 Docker（推荐快速开始）**

```bash
cd backend
docker-compose up -d postgres redis
```

优点：
- 一键启动，无需配置
- 自动包含 pgvector 扩展
- 隔离性好，不影响系统

**方式二：本地安装（推荐生产环境）**

确保以下服务正在运行：
- PostgreSQL 15+ (localhost:5432)
  - 数据库: echoman
  - 用户: echoman
  - 密码: echoman_password
  - 需安装 pgvector 扩展
- Redis 6+ (localhost:6379)

📖 **详细安装教程**: 查看 [INSTALL_LOCAL_DATABASE.md](./INSTALL_LOCAL_DATABASE.md)

优点：
- 完全控制数据库配置
- 更好的性能（无虚拟化开销）
- 适合长期运行

#### 1.3 验证数据库连接

```bash
# 测试 PostgreSQL
psql -h localhost -U echoman -d echoman -c "SELECT version();"

# 测试 Redis
redis-cli ping
```

### 步骤 2: 安装依赖

```bash
cd backend
pip install -r requirements.txt
```

### 步骤 3: 初始化数据库

```bash
cd backend
python scripts/init_tables.py create
```

可用命令：
- `create` - 创建数据库表
- `drop` - 删除数据库表（危险操作）
- `recreate` - 重新创建数据库表

### 步骤 4: 启动 FastAPI 服务

```bash
cd backend
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

或者使用项目根目录的启动脚本：

```bash
python backend.py
```

## 🔧 服务管理

### 启动选项

`backend.py` 支持多种启动模式：

```bash
# 启动所有服务（API + Worker + Beat）
python backend.py --all

# 仅启动 API 服务器
python backend.py --api

# 仅启动 Celery Worker
python backend.py --worker

# 仅启动 Celery Beat
python backend.py --beat

# 启动 API 和 Worker（不启动定时任务）
python backend.py --api --worker

# 跳过数据库检查（不推荐）
python backend.py --all --no-check

# 查看帮助
python backend.py --help
```

### 自动采集时间表

启动 Celery Beat 后，系统会按以下时间自动采集：

| 时间 | 任务类型 |
|------|---------|
| 08:00 | 数据采集 |
| 10:00 | 数据采集 |
| 12:00 | 数据采集 |
| 12:15 | 上半日归并 |
| 12:30 | 整体归并 |
| 14:00 | 数据采集 |
| 16:00 | 数据采集 |
| 18:00 | 数据采集 |
| 20:00 | 数据采集 |
| 22:00 | 数据采集 |
| 22:15 | 下半日归并 |
| 22:30 | 整体归并 |

### 启动 Flower 监控（可选）

用于监控 Celery 任务：

```bash
cd backend
conda activate echoman
celery -A app.tasks.celery_app flower --port=5555
```

访问: http://localhost:5555

### 手动管理服务（不推荐）

如果你需要完全手动控制，可以分别启动各服务：

```bash
# 终端 1: API 服务器
cd backend
conda activate echoman
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# 终端 2: Celery Worker
cd backend
conda activate echoman
celery -A app.tasks.celery_app worker --loglevel=info

# 终端 3: Celery Beat
cd backend
conda activate echoman
celery -A app.tasks.celery_app beat --loglevel=info
```

**注意：推荐使用 `python backend.py --all` 来一次性启动所有服务。**

## 🛠️ 常用命令

### 查看数据库表

```bash
# 进入 PostgreSQL
psql -h localhost -U echoman -d echoman

# 查看所有表
\dt

# 查看表结构
\d source_items
\d topics

# 退出
\q
```

### 查看 Redis 数据

```bash
# 进入 Redis CLI
redis-cli

# 查看所有键
KEYS *

# 退出
exit
```

### 查看日志

```bash
# 如果使用 Docker 启动数据库
docker-compose logs -f postgres
docker-compose logs -f redis

# FastAPI 日志会直接输出到终端
```

## ⚙️ 环境配置

### 配置文件位置

- 主配置: `backend/app/config/settings.py`
- 环境变量: `backend/.env`（可选，优先级高于默认值）

### 关键配置项

```python
# 数据库配置
DB_HOST=localhost
DB_PORT=5432
DB_USER=echoman
DB_PASSWORD=echoman_password
DB_NAME=echoman

# Redis 配置
REDIS_HOST=localhost
REDIS_PORT=6379

# Chroma 向量数据库配置
VECTOR_DB_TYPE=chroma
CHROMA_PERSIST_DIRECTORY=./data/chroma
CHROMA_COLLECTION_NAME=echoman_embeddings
EMBEDDING_DIMENSION=4096  # Qwen3-Embedding-8B

# 采集配置
ENABLED_PLATFORMS=weibo,zhihu,toutiao,sina,netease,baidu,hupu
FETCH_LIMIT_PER_PLATFORM=30

# LLM 配置（待实现功能使用）
LLM_PROVIDER=qwen
QWEN_MODEL=qwen3-32b
QWEN_API_BASE=http://localhost:8000/v1
```

## 🐛 常见问题

### 1. 端口 8000 已被占用

```bash
# 查找占用端口的进程
lsof -i :8000

# 杀死进程
kill -9 <PID>

# 或使用不同端口启动
uvicorn app.main:app --reload --host 0.0.0.0 --port 8001
```

### 2. 数据库连接失败

检查 PostgreSQL 是否运行：

```bash
# 使用 Docker
docker-compose ps
docker-compose logs postgres

# 本地服务
sudo systemctl status postgresql
```

### 3. Redis 连接失败

检查 Redis 是否运行：

```bash
# 使用 Docker
docker-compose ps
docker-compose logs redis

# 本地服务
sudo systemctl status redis
```

### 4. 依赖安装失败

```bash
# 升级 pip
pip install --upgrade pip

# 重新安装依赖
pip install -r requirements.txt --force-reinstall
```

### 5. 数据库表创建失败

```bash
# 手动创建 pgvector 扩展
psql -h localhost -U echoman -d echoman -c "CREATE EXTENSION IF NOT EXISTS vector;"

# 重新创建表
python scripts/init_tables.py recreate
```

## 📚 下一步

启动成功后，可以：

1. **测试采集功能**: 访问 http://localhost:8000/docs 并尝试 `/api/v1/ingest/run` 接口
2. **查看数据**: 使用 psql 查看 `source_items` 表中的采集数据
3. **开发新功能**: 参考 `BACKEND_README.md` 和 `PROJECT_STATUS.md`
4. **启动前端**: 运行 `python frontend.py` 启动前端界面

## 🔗 相关文档

- [完整 README](./BACKEND_README.md) - 详细的功能说明和架构介绍
- [项目状态](./PROJECT_STATUS.md) - 当前实现进度和待办事项
- [API 规范](../docs/api-spec.md) - API 接口文档
- [方案设计](../docs/backend-solution.md) - 后端设计方案

## 💡 提示

- 默认情况下，FastAPI 会自动重载代码更改（`--reload` 模式）
- 可以通过访问 `/docs` 查看交互式 API 文档
- Celery Worker 和 Beat 需要单独启动才能使用定时任务功能
- 目前归并、LLM 等高级功能尚未实现，但基础采集和 API 功能已就绪

