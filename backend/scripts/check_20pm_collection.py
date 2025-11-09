"""
检查20点采集任务情况
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import asyncio
from sqlalchemy import text
from app.core.database import get_async_session


async def check():
    """检查20点采集任务"""
    async_session = get_async_session()
    
    async with async_session() as session:
        print("检查20点采集任务...")
        print()
        
        # 1. 检查20点的run记录
        print("【1. 20点采集任务Run记录】")
        result = await session.execute(text("""
            SELECT id, status, started_at, completed_at,
                   items_total, items_success, items_failed,
                   error_message
            FROM runs_pipeline
            WHERE stage = 'ingestion'
                AND started_at >= '2025-11-07 20:00:00'
                AND started_at < '2025-11-07 21:00:00'
            ORDER BY started_at DESC;
        """))
        
        runs = result.fetchall()
        if runs:
            for run in runs:
                status_icon = "✅" if run[1] == "success" else "❌"
                print(f"{status_icon} Run ID: {run[0]}")
                print(f"   状态: {run[1]}")
                print(f"   时间: {run[2]} - {run[3]}")
                print(f"   数据: {run[5]}/{run[4]} 成功")
                if run[7]:
                    print(f"   错误: {run[7]}")
                print()
        else:
            print("  ⚠️  无20点采集任务记录")
        
        # 2. 检查EVE周期数据
        print("【2. EVE周期数据统计】")
        result = await session.execute(text("""
            SELECT merge_status, COUNT(*) as count
            FROM source_items
            WHERE period = '2025-11-07_EVE'
            GROUP BY merge_status
            ORDER BY count DESC;
        """))
        
        statuses = result.fetchall()
        if statuses:
            total = sum(row[1] for row in statuses)
            print(f"总数据: {total} 条")
            for row in statuses:
                print(f"  {row[0]:25s}: {row[1]:3d} 条 ({row[1]/total*100:.1f}%)")
        else:
            print("  ⚠️  无EVE周期数据")
        print()
        
        # 3. 检查EVE周期embedding状态
        print("【3. EVE周期Embedding状态】")
        result = await session.execute(text("""
            SELECT COUNT(*) as total,
                   COUNT(embedding_id) as has_embedding,
                   COUNT(DISTINCT period_merge_group_id) as merge_groups
            FROM source_items
            WHERE period = '2025-11-07_EVE'
                AND merge_status = 'pending_event_merge';
        """))
        
        row = result.fetchone()
        if row and row[0] > 0:
            print(f"pending_event_merge数据: {row[0]} 条")
            print(f"  有embedding: {row[1]} 条 ({row[1]/row[0]*100:.1f}%)")
            print(f"  归并组: {row[2]} 个")
        else:
            print("  ✅ 无待处理数据")
        print()
        
        # 4. 检查20-22点的采集时间分布
        print("【4. 20-22点采集时间分布】")
        result = await session.execute(text("""
            SELECT DATE_TRUNC('hour', fetched_at) as hour,
                   COUNT(*) as count
            FROM source_items
            WHERE fetched_at >= '2025-11-07 20:00:00'
                AND fetched_at < '2025-11-07 23:00:00'
            GROUP BY DATE_TRUNC('hour', fetched_at)
            ORDER BY hour;
        """))
        
        hours = result.fetchall()
        if hours:
            for row in hours:
                print(f"  {row[0]}: {row[1]} 条")
        else:
            print("  ⚠️  无20-22点采集数据")


if __name__ == "__main__":
    asyncio.run(check())

