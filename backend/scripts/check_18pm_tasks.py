"""
检查18点PM周期的采集和归并任务情况
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import asyncio
from sqlalchemy import text
from app.core.database import get_async_session
from datetime import datetime, timedelta


async def check():
    """检查18点相关任务"""
    async_session = get_async_session()
    
    async with async_session() as session:
        print("=" * 60)
        print("18点PM周期任务检查")
        print("=" * 60)
        
        # 1. 检查18点的采集任务
        print("\n1. 18:00采集任务:")
        result = await session.execute(text("""
            SELECT 
                run_id,
                status,
                started_at,
                total_items,
                success_items,
                failed_items
            FROM runs_ingest 
            WHERE DATE(started_at) = CURRENT_DATE 
                AND EXTRACT(HOUR FROM started_at) = 18
            ORDER BY started_at DESC
            LIMIT 1;
        """))
        
        row = result.fetchone()
        if row:
            print(f"  Run ID: {row[0]}")
            print(f"  状态: {row[1]}")
            print(f"  时间: {row[2]}")
            print(f"  数据: 采集{row[3]}条, 成功{row[4]}条, 失败{row[5]}条")
        else:
            print("  ❌ 未找到18点采集记录")
        
        # 2. 检查18点采集的数据
        print("\n2. 18点采集数据统计:")
        result = await session.execute(text("""
            SELECT 
                platform,
                COUNT(*) as count,
                period,
                merge_status
            FROM source_items 
            WHERE DATE(fetched_at) = CURRENT_DATE
                AND EXTRACT(HOUR FROM fetched_at) = 18
            GROUP BY platform, period, merge_status
            ORDER BY platform;
        """))
        
        rows = result.fetchall()
        if rows:
            for row in rows:
                print(f"  {row[0]:10} | {row[2]:20} | {row[3]:25} | {row[1]:3}条")
        else:
            print("  （无数据）")
        
        # 3. 检查PM周期的总数据量
        print("\n3. PM周期（14:00-18:00）总数据:")
        result = await session.execute(text("""
            SELECT 
                COUNT(*) as total,
                COUNT(DISTINCT platform) as platforms,
                COUNT(CASE WHEN merge_status = 'pending_event_merge' THEN 1 END) as pending,
                COUNT(CASE WHEN merge_status = 'pending_global_merge' THEN 1 END) as ready_global,
                COUNT(CASE WHEN merge_status = 'merged' THEN 1 END) as merged,
                COUNT(CASE WHEN merge_status = 'discarded' THEN 1 END) as discarded
            FROM source_items 
            WHERE period LIKE '%_PM'
                AND DATE(fetched_at) = CURRENT_DATE;
        """))
        
        row = result.fetchone()
        if row:
            print(f"  总数: {row[0]} 条")
            print(f"  平台数: {row[1]} 个")
            print(f"  状态分布:")
            print(f"    - pending_event_merge: {row[2]} 条")
            print(f"    - pending_global_merge: {row[3]} 条")
            print(f"    - merged: {row[4]} 条")
            print(f"    - discarded: {row[5]} 条")
        
        # 4. 检查PM周期的归并结果
        print("\n4. PM周期归并生成的主题:")
        result = await session.execute(text("""
            SELECT 
                t.id,
                t.title_key,
                t.first_seen,
                t.last_active,
                COUNT(DISTINCT tn.source_item_id) as source_count
            FROM topics t
            LEFT JOIN topic_nodes tn ON t.id = tn.topic_id
            WHERE DATE(t.last_active) = CURRENT_DATE
                AND EXTRACT(HOUR FROM t.last_active) >= 18
            GROUP BY t.id, t.title_key, t.first_seen, t.last_active
            ORDER BY t.last_active DESC
            LIMIT 10;
        """))
        
        rows = result.fetchall()
        if rows:
            print(f"  今日18点后活跃的主题（最多10个）:")
            for row in rows:
                print(f"    - {row[1][:50]:50} | 来源: {row[4]}条 | 最后活跃: {row[3]}")
        else:
            print("  （暂无18点后活跃的主题）")
        
        # 5. 检查PM周期热度记录
        print("\n5. PM周期热度记录:")
        result = await session.execute(text("""
            SELECT 
                COUNT(*) as count,
                SUM(source_count) as total_sources
            FROM topic_period_heat 
            WHERE period = 'PM'
                AND date = CURRENT_DATE;
        """))
        
        row = result.fetchone()
        if row and row[0]:
            print(f"  已生成 {row[0]} 个主题的PM周期热度记录")
            print(f"  共关联 {row[1]} 条源数据")
        else:
            print("  ⚠️  暂无PM周期热度记录")


if __name__ == "__main__":
    asyncio.run(check())

