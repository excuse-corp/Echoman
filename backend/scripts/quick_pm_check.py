"""
快速检查PM周期归并为什么失败
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
        print("检查PM周期数据状态...")
        
        # 1. 检查pending_event_merge的数据（热度归一化后应该已处理）
        result = await session.execute(text("""
            SELECT COUNT(*), 
                   COUNT(CASE WHEN heat_normalized IS NOT NULL THEN 1 END) as has_heat,
                   MIN(heat_normalized) as min_heat,
                   MAX(heat_normalized) as max_heat
            FROM source_items 
            WHERE period = '2025-11-07_PM'
                AND merge_status = 'pending_event_merge';
        """))
        
        row = result.fetchone()
        print(f"\nPending数据: {row[0]} 条")
        print(f"  有热度值: {row[1]} 条")
        print(f"  热度范围: {row[2]:.6f} ~ {row[3]:.6f}" if row[1] > 0 else "  无热度数据")
        
        # 2. 检查是否有向量embedding
        result = await session.execute(text("""
            SELECT COUNT(*), COUNT(embedding_id)
            FROM source_items 
            WHERE period = '2025-11-07_PM'
                AND merge_status = 'pending_event_merge';
        """))
        
        row = result.fetchone()
        print(f"\nEmbedding状态: {row[1]}/{row[0]} 条有向量ID")
        
        # 3. 查看一些样本
        result = await session.execute(text("""
            SELECT id, platform, title, heat_normalized, embedding_id
            FROM source_items 
            WHERE period = '2025-11-07_PM'
                AND merge_status = 'pending_event_merge'
            LIMIT 5;
        """))
        
        print("\n样本数据:")
        for row in result.fetchall():
            print(f"  ID:{row[0]} | {row[1]:10} | {row[3]:.6f} | EMB:{row[4]} | {row[2][:40]}")


if __name__ == "__main__":
    asyncio.run(check())

