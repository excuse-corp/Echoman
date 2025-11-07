#!/bin/bash

echo "🛑 停止后端服务..."
pkill -f "uvicorn app.main:app"
sleep 2

echo "🚀 启动后端服务..."
cd /root/ren/Echoman/backend
conda run -n echoman uvicorn app.main:app --host 0.0.0.0 --port 8778 --reload > /tmp/backend.log 2>&1 &

echo "⏳ 等待服务启动..."
sleep 5

echo "✅ 测试API..."
curl -s "http://127.0.0.1:8778/api/v1/topics?page=1&size=1" | python3 -m json.tool 2>/dev/null | grep -E "intensity_norm|length_hours"

echo ""
echo "📋 查看日志："
echo "tail -f /tmp/backend.log"

