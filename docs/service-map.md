# 服务路径与端口一览

| 服务 | 启动脚本 / 命令 | 主要端口 | 说明 |
| --- | --- | --- | --- |
| FastAPI API | `python backend.py --api` 或 `start.sh` | 8778 | 主 REST 接口，健康检查 `/health` |
| Celery Worker | `python backend.py --worker` 或 `start.sh` | N/A | 执行异步采集、归并等任务 |
| Celery Beat | `python backend.py --beat` 或 `start.sh` | N/A | 定时任务调度（采集与归并） |
| PostgreSQL | `cd backend && docker-compose up -d postgres` 或 `start.sh` | 5432 | 业务数据库 |
| Redis | `cd backend && docker-compose up -d redis` 或 `start.sh` | 6379 | Celery broker / cache |
| Chroma | **嵌入式（默认）** | N/A | 进程内持久化（`./data/chroma`） |

## 常用一键脚本

- `./start.sh`：后台启动 API + Worker + Beat，并自动启动 PostgreSQL/Redis（docker-compose），日志写入 `backend_services.log`。
- `./stop.sh`：尝试终止 API/Worker/Beat 及相关 docker 数据库容器。

## 其他路径

- 后端代码根目录：`backend/`
- 前端代码根目录：`frontend/`
- 运行日志：`backend_services.log`（start.sh 生成），`frontend.log`
