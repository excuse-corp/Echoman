#!/bin/bash

echo "=========================================="
echo "  10点数据验证脚本"
echo "  Data Verification for 10:00 Period"
echo "=========================================="
echo ""

# 1. 检查Period格式
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "1️⃣  检查今日Period格式"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
psql -U echoman -d echoman -c "
SELECT 
    halfday_period,
    COUNT(*) as item_count,
    MIN(created_at) as first_item,
    MAX(created_at) as last_item
FROM source_items 
WHERE halfday_period LIKE '2025-11-07_%' 
GROUP BY halfday_period 
ORDER BY halfday_period DESC
LIMIT 10;
"
echo ""

# 2. 检查10点采集数据
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "2️⃣  检查10点时段数据"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
psql -U echoman -d echoman -c "
SELECT 
    platform,
    COUNT(*) as count,
    MIN(title) as sample_title
FROM source_items 
WHERE halfday_period = '2025-11-07_10'
GROUP BY platform;
"
echo ""

# 3. 检查10点归并结果
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "3️⃣  检查10点时段的Topic"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
psql -U echoman -d echoman -c "
SELECT 
    t.id,
    t.title_key,
    t.category,
    COUNT(DISTINCT tn.id) as node_count,
    t.created_at
FROM topics t
LEFT JOIN topic_nodes tn ON tn.topic_id = t.id
WHERE t.created_at >= '2025-11-07 10:00:00'
  AND t.created_at < '2025-11-07 11:00:00'
GROUP BY t.id, t.title_key, t.category, t.created_at
ORDER BY t.created_at DESC
LIMIT 10;
"
echo ""

# 4. 检查最新Topic更新时间
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "4️⃣  最新更新的Topic"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
psql -U echoman -d echoman -c "
SELECT 
    id,
    title_key,
    category,
    updated_at,
    created_at
FROM topics 
ORDER BY updated_at DESC 
LIMIT 5;
"
echo ""

# 5. 前端API测试
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "5️⃣  前端API测试"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "热榜Top 5:"
curl -s http://localhost:8778/api/v1/topics/hottest?limit=5 | python3 -m json.tool | grep -E "title_key|intensity_norm|updated_at" | head -15
echo ""

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✅ 验证完成"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "📌 前端验证："
echo "   打开浏览器访问: http://your-domain:3000/explore"
echo "   刷新页面查看最新热榜数据"
echo ""

