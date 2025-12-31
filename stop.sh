#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT_DIR"

PID_FILE="$ROOT_DIR/backend_services.pid"

echo "==> 停止后端服务 ..."

# 优雅终止通过 backend.py 启动的主进程
if [[ -f "$PID_FILE" ]]; then
  PID=$(cat "$PID_FILE")
  if kill -0 "$PID" 2>/dev/null; then
    kill "$PID" || true
    sleep 2
  fi
  rm -f "$PID_FILE"
fi

# 兜底清理可能残留的子进程
pkill -f "uvicorn app.main:app" >/dev/null 2>&1 || true
pkill -f "celery -A app.tasks.celery_app [w]orker" >/dev/null 2>&1 || true
pkill -f "celery -A app.tasks.celery_app [b]eat" >/dev/null 2>&1 || true

# 可选：停止数据库容器
(cd backend && docker-compose stop postgres redis >/dev/null 2>&1 || true)

echo "所有相关服务已尝试停止。"
