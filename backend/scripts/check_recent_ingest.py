"""
检查最近的采集情况
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import asyncio
from sqlalchemy import text
from app.core.database import get_async_session


async def check():
    """检查采集情况"""
    async_session = get_async_session()
    
    async with async_session() as session:
        print("=" * 60)
        print("最近采集情况检查")
        print("=" * 60)
        
        # 1. 检查今天16点后的采集数据
        print("\n1. 今天16:00之后的采集数据:")
        result = await session.execute(text("""
            SELECT 
                DATE_TRUNC('hour', fetched_at) as hour,
                period,
                COUNT(*) as count,
                COUNT(DISTINCT platform) as platforms
            FROM source_items 
            WHERE DATE(fetched_at) = CURRENT_DATE 
                AND fetched_at >= CURRENT_DATE + INTERVAL '16 hours'
            GROUP BY hour, period
            ORDER BY hour;
        """))
        
        rows = result.fetchall()
        if rows:
            for row in rows:
                print(f"  {row[0]} - {row[1]}: {row[2]} 条数据，{row[3]} 个平台")
        else:
            print("  （无数据）")
        
        # 2. 检查最近的采集运行
        print("\n2. 最近的采集运行:")
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
                AND started_at >= CURRENT_DATE + INTERVAL '16 hours'
            ORDER BY started_at DESC
            LIMIT 5;
        """))
        
        rows = result.fetchall()
        if rows:
            for row in rows:
                print(f"  {row[0]}: {row[1]} - 成功{row[4]}/{row[3]}, 失败{row[5]}")
                print(f"    时间: {row[2]}")
        else:
            print("  （无运行记录）")
        
        # 3. 检查16点的采集数据详情
        print("\n3. 16:00-16:59的数据详情:")
        result = await session.execute(text("""
            SELECT 
                platform,
                merge_status,
                COUNT(*) as count
            FROM source_items 
            WHERE fetched_at >= CURRENT_DATE + INTERVAL '16 hours'
                AND fetched_at < CURRENT_DATE + INTERVAL '17 hours'
            GROUP BY platform, merge_status
            ORDER BY platform, merge_status;
        """))
        
        rows = result.fetchall()
        if rows:
            for row in rows:
                print(f"  {row[0]} - {row[1]}: {row[2]} 条")
        else:
            print("  （无数据）")
        
        # 4. 检查period字段是否正确设置
        print("\n4. 今天各时段的数据分布:")
        result = await session.execute(text("""
            SELECT 
                period,
                COUNT(*) as count,
                MIN(fetched_at) as first_time,
                MAX(fetched_at) as last_time
            FROM source_items 
            WHERE DATE(fetched_at) = CURRENT_DATE
            GROUP BY period
            ORDER BY period;
        """))
        
        rows = result.fetchall()
        if rows:
            for row in rows:
                print(f"  {row[0]}: {row[1]} 条 ({row[2]} ~ {row[3]})")
        else:
            print("  （无数据）")


if __name__ == "__main__":
    asyncio.run(check())

