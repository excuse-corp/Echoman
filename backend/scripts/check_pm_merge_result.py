"""
检查PM归并结果
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import asyncio
from sqlalchemy import text
from app.core.database import get_async_session


async def check():
    """检查"""
    async_session = get_async_session()
    
    async with async_session() as session:
        print("检查PM周期归并结果...")
        print()
        
        # 1. 按merge_status统计
        print("【merge_status分布】")
        result = await session.execute(text("""
            SELECT merge_status, COUNT(*) as count
            FROM source_items 
            WHERE period = '2025-11-07_PM'
            GROUP BY merge_status
            ORDER BY count DESC;
        """))
        for row in result:
            print(f"  {row[0]:25s}: {row[1]:3d} 条")
        print()
        
        # 2. 检查pending_global_merge数据（应该是阶段一完成后的数据）
        print("【pending_global_merge数据】")
        result = await session.execute(text("""
            SELECT COUNT(*),
                   COUNT(period_merge_group_id) as has_group,
                   COUNT(DISTINCT period_merge_group_id) as unique_groups
            FROM source_items 
            WHERE period = '2025-11-07_PM'
                AND merge_status = 'pending_global_merge';
        """))
        row = result.fetchone()
        if row and row[0] > 0:
            print(f"  总数: {row[0]} 条")
            print(f"  有归并组ID: {row[1]} 条")
            print(f"  归并组数量: {row[2]} 个")
        else:
            print("  无数据")
        print()
        
        # 3. 检查merged数据（应该是阶段二完成后的数据）
        print("【merged数据】")
        result = await session.execute(text("""
            SELECT COUNT(*),
                   COUNT(DISTINCT period_merge_group_id) as unique_groups
            FROM source_items 
            WHERE period = '2025-11-07_PM'
                AND merge_status = 'merged';
        """))
        row = result.fetchone()
        if row and row[0] > 0:
            print(f"  总数: {row[0]} 条")
            print(f"  归并组数量: {row[1]} 个")
        else:
            print("  无数据")
        print()
        
        # 4. 检查discarded数据（应该是被丢弃的噪音数据）
        print("【discarded数据】")
        result = await session.execute(text("""
            SELECT COUNT(*)
            FROM source_items 
            WHERE period = '2025-11-07_PM'
                AND merge_status = 'discarded';
        """))
        row = result.fetchone()
        print(f"  总数: {row[0]} 条")
        print()
        
        # 5. 检查topic表（看是否有新topic）
        print("【Topic数据】")
        result = await session.execute(text("""
            SELECT COUNT(*)
            FROM topics
            WHERE created_at >= '2025-11-07 18:00:00';
        """))
        row = result.fetchone()
        print(f"  18点后创建的topic: {row[0]} 个")


if __name__ == "__main__":
    asyncio.run(check())

