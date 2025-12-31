#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT_DIR"

LOG_FILE="$ROOT_DIR/backend_services.log"
PID_FILE="$ROOT_DIR/backend_services.pid"

echo "==> 启动后端服务 (API + Worker + Beat + DB) ..."
nohup python backend.py --all --db --restart-celery >"$LOG_FILE" 2>&1 &
echo $! > "$PID_FILE"

echo "后台运行中，PID=$(cat "$PID_FILE")"
echo "日志: $LOG_FILE"
