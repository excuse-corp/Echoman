#!/bin/bash

# 完成PM周期的全局归并
cd /root/ren/Echoman/backend
source /root/anaconda3/etc/profile.d/conda.sh
conda activate echoman

echo "开始完成PM周期的全局归并..."
echo "====================================="

round=10
max_rounds=20

while [ $round -le $max_rounds ]; do
    echo ""
    echo "【第 $round 轮归并】"
    
    # 执行归并
    python scripts/manual_trigger_global_merge.py 2025-11-07_PM 2>&1 | grep -E "归并完成|merge=" | tail -2
    
    # 检查pending数量
    pending=$(python -c "
import sys
sys.path.insert(0, '.')
import asyncio
from sqlalchemy import text
from app.core.database import get_async_session

async def check():
    async_session = get_async_session()
    async with async_session() as session:
        result = await session.execute(text(
            \"SELECT COUNT(*) FROM source_items WHERE period = '2025-11-07_PM' AND merge_status = 'pending_global_merge'\"
        ))
        return result.scalar()

print(asyncio.run(check()))
" 2>/dev/null)
    
    echo "剩余待处理: $pending 条"
    
    # 如果没有待处理数据，退出
    if [ "$pending" -le "0" ]; then
        echo ""
        echo "✅ 所有数据已处理完成！"
        break
    fi
    
    round=$((round + 1))
    sleep 2
done

echo ""
echo "====================================="
echo "最终统计："
python scripts/check_pm_merge_result.py 2>&1 | grep -E "merge_status|pending_global_merge|merged|discarded|Topic数据"

