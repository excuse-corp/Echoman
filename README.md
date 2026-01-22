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
- **监控接口**：健康检查、Prometheus 指标（见下方 API）

## 快速启动（本机开发）

### 前置要求

- Python 3.11+（项目脚本默认使用 `conda` 环境名 `echoman`）
- Node.js 18+
- Docker + Docker Compose（用于一键启动 PostgreSQL/Redis；也可手动本地安装）

### 1) 配置后端环境变量

后端运行时读取 `backend/.env`（见 `backend/env.template`）。

```bash
cp backend/env.template backend/.env
```

最少需要确认：
- `DB_*`（默认 `echoman / echoman_password / echoman`）
- `LLM_PROVIDER` 与对应的 `*_API_KEY`/`*_BASE_URL`
- `VECTOR_DB_TYPE`（默认 `chroma`，使用本地持久化目录 `backend/data/chroma/`）

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
- 分类与指标
  - `GET /api/v1/categories`：分类列表
  - `GET /api/v1/categories/metrics/summary`：分类统计摘要
- 监控
  - `GET /api/v1/monitoring/monitoring/health`
  - `GET /api/v1/monitoring/monitoring/metrics`

> 说明：当前 `monitoring` 路由在代码中同时设置了 include 前缀与 router 前缀，因此实际路径为 `.../monitoring/monitoring/...`。

## 运行脚本与日志

- `start.sh`：后台启动 `python backend.py --all --db --restart-celery`，日志 `backend_services.log`，PID `backend_services.pid`
- `stop.sh`：尝试停止 uvicorn/celery，并可选停止 `backend/docker-compose.yml` 中的数据库容器
- `backend.py`：后端服务管理器（API/Worker/Beat 任意组合）
- `frontend.py`：前端开发服务器启动器（缺依赖时自动 `npm install`）

## 技术栈（按仓库代码实际使用）

- 后端：FastAPI、SQLAlchemy（async）、Celery、PostgreSQL、Redis、Chroma（`chromadb.PersistentClient`）
- 前端：React、React Router、Vite、TypeScript（无 UI 组件库，原生 CSS）

## 项目结构

```
Echoman/
├── backend.py
├── frontend.py
├── start.sh
├── stop.sh
├── HOW_TO_START.md
├── backend/
│   ├── app/                 # FastAPI 应用（api/models/services/tasks...）
│   ├── scrapers/            # 7个平台热点爬虫
│   ├── scripts/             # 初始化与批处理脚本
│   ├── docker-compose.yml   # PostgreSQL/Redis +（可选）服务编排
│   ├── env.template         # 后端环境变量模板
│   └── data/                # 本地数据（含 chroma 持久化目录）
├── frontend/
│   ├── src/
│   ├── vite.config.ts       # dev server proxy: /api/v1 -> 8778
│   └── .env.development
└── docs/
    ├── api-spec.md
    ├── backend-solution.md
    ├── merge-logic.md
    ├── ECHO_METRICS_CALCULATION.md
    └── 数据流转架构.md
```

## 文档导航

- `HOW_TO_START.md`：启动指南（含脚本说明与常见问题）
- `docs/service-map.md`：端口与服务一览（如有出入，以代码/脚本为准）
- `docs/merge-logic.md`：归并逻辑说明
- `docs/ECHO_METRICS_CALCULATION.md`：回声指标计算说明
- `docs/api-spec.md`：API 规范（更偏文档化描述）

## 注意事项（务必读）

- **依赖清单缺失**：仓库当前未包含 `backend/requirements.txt`，因此 `backend/Dockerfile` 与 `backend.py` 的“自动安装依赖”步骤在全新环境中会失败。若需 Docker 化或从零安装，请先补齐依赖清单，或在 `conda echoman` 环境中手动安装项目依赖后再启动。
- **脚本强依赖 conda 路径**：`backend.py`/`frontend.py` 默认 `source /root/anaconda3/etc/profile.d/conda.sh && conda activate echoman`；如你的 conda 安装路径或环境名不同，请按实际修改。
- **前端有 fallback 数据**：当前前端在请求后端失败时会回退到内置示例数据（用于 UI 演示与开发），排查时请以浏览器 Network 与后端 `/docs` 为准。
- **不要提交密钥**：请将 `backend/.env` 视为本地配置文件，避免提交包含 API Key 的版本。
  - **Celery Beat 调度文件**：`backend/celerybeat-schedule.*` 为调度持久化文件，可删除重建；不要手改。

## 贡献

欢迎提交 Issue / PR（建议同时更新相关 `docs/` 与接口说明）。

## 许可证

MIT
