# Echoman - 热点事件聚合与回声追踪系统

Echoman 是一个“多平台热点 → 归并为话题 → 追踪传播回声 → 支持 RAG 问答”的全栈项目，包含：
- 后端：FastAPI + Celery + PostgreSQL + **Chroma 向量检索（现网口径）**
- 前端：React + Vite（内置对后端的 `/api/v1` 代理，支持 SSE 流式对话）

## 功能概览

- **多平台热点采集（7个平台）**：`weibo / zhihu / toutiao / sina / netease / baidu / hupu`
- **两层归并**：阶段一归并（向量/相似度聚类 + LLM 判定）→ 阶段二归并（话题合并/新建）
- **四个归并时段**：MORN/AM/PM/EVE（08:05/12:05/18:05/22:05 触发阶段一；08:20/12:20/18:20/22:20 触发阶段二）
- **采集噪音过滤**：拦截误操作条目（如“点击查看更多实时热点”及热榜列表页链接）
- **回声指标**：回声长度（话题持续时间）、强度等统计指标（前端用于排序/展示）
- **分类与指标**：三分类（娱乐/社会时事/体育电竞）+ 分类聚合统计
- **RAG 对话**：`topic/global` 双模式，支持 **SSE 流式输出**
- **自由模式**：需要邀请码换取 `free_token`，`mode=global` 时后端强校验


## 系统流程（概览）

```
采集（8次/天） → 噪音过滤 → 阶段一归并（向量/标题聚类 + LLM判定）
             → 出现次数筛选（>=2） → 阶段二归并（召回历史话题 + LLM判定）
             → 话题摘要/分类/热度 → 前端展示
```

## 快速启动（本机开发）

### 前置要求

- Python 3.11+
- Node.js 18+
- Docker + Docker Compose（用于一键启动 PostgreSQL/Redis）

### 1) 配置后端环境变量

后端运行时读取 `.env`（见 `env.template`）。

```bash
cp env.template .env
```

最少需要确认：
- `DB_*`（默认 `echoman / echoman_password / echoman`）
- `LLM_PROVIDER` 与对应的 `*_API_KEY`/`*_BASE_URL`
- `VECTOR_DB_TYPE`（默认 `chroma`，使用本地持久化目录 `backend/data/chroma/`）
- 自由模式相关：`FREE_MODE_INVITE_TTL_DAYS`、`FREE_MODE_TOKEN_TTL_HOURS`

> LLM 详细配置（Qwen/OpenAI/Azure/OpenAI Compatible）请看：`HOW_TO_START.md` 的 **LLM 配置** 部分。

### 2) 启动后端（API + Worker + Beat + DB）

推荐一键脚本（后台运行，日志写入 `backend_services.log`）：

```bash
./start.sh
```

停止：

```bash
./stop.sh
```

或前台精细控制：

```bash
python backend.py --all --db --restart-celery
```

> 说明：数据库初始化会自动创建自由模式相关表与 `topic_item_mv` 物化视图，无需额外迁移脚本。

后端默认端口：`8778`

### 3) 启动前端

```bash
python frontend.py
```

前端默认端口：`5173`

### 4) 访问

- 前端：http://localhost:5173
- 后端 Swagger：http://localhost:8778/docs
- 后端健康检查：http://localhost:8778/health

## API（常用）

> 路径前缀为 `/api/v1`（由后端配置 `api_v1_prefix` 决定）。

- 采集
  - `POST /api/v1/ingest/run`：手动触发采集（platforms/limit）
  - `GET /api/v1/ingest/runs`：采集历史
  - `GET /api/v1/ingest/sources/status`：平台连接器状态
- 话题
  - `GET /api/v1/topics`：话题列表（支持筛选/排序/分页）
  - `GET /api/v1/topics/today`：当日话题
  - `GET /api/v1/topics/{topic_id}`：话题详情
  - `GET /api/v1/topics/{topic_id}/timeline`：时间线
- 对话（RAG）
  - `POST /api/v1/chat/ask`：问答（`stream=true` 时返回 SSE 事件流）
  - `POST /api/v1/chat/create`：创建会话
- 自由模式
  - `POST /api/v1/free/verify`：邀请码校验并返回 `free_token`
- 分类与指标
  - `GET /api/v1/categories`：分类列表
  - `GET /api/v1/categories/metrics/summary`：分类统计摘要
- 监控
  - `GET /api/v1/monitoring/monitoring/health`
  - `GET /api/v1/monitoring/monitoring/metrics`

> 说明：当前 `monitoring` 路由在代码中同时设置了 include 前缀与 router 前缀，因此实际路径为 `.../monitoring/monitoring/...`。

## 运营与数据维护

- **噪音数据清理脚本**：`backend/scripts/cleanup_noise_items.py`
  - 默认 dry-run，使用 `--apply` 执行删除（含 Topic/SourceItem/向量清理）
- **Chroma 数据目录**：`backend/data/chroma/`（本地持久化）
- **Celery Beat 调度文件**：`backend/celerybeat-schedule.*` 为调度状态存储，可删除重建；不要手改

## 运行脚本与日志

- `start.sh`：后台启动 `python backend.py --all --db --restart-celery`，日志 `backend_services.log`，PID `backend_services.pid`
- `stop.sh`：尝试停止 uvicorn/celery，并可选停止 `backend/docker-compose.yml` 中的数据库容器
- `backend.py`：后端服务管理器（API/Worker/Beat 任意组合）
- `frontend.py`：前端开发服务器启动器（缺依赖时自动 `npm install`）



## 许可证

Apache-2.0
