"""
清理重复的embedding记录，只保留每个source_item的最新embedding
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import asyncio
from sqlalchemy import text
from app.core.database import get_async_session


async def cleanup():
    """清理重复的embedding"""
    async_session = get_async_session()
    
    async with async_session() as session:
        print("检查重复的embedding...")
        
        # 1. 查找有多个embedding的source_item
        result = await session.execute(text("""
            SELECT object_id, COUNT(*) as count
            FROM embeddings
            WHERE object_type = 'source_item'
            GROUP BY object_id
            HAVING COUNT(*) > 1
            ORDER BY count DESC
            LIMIT 10;
        """))
        
        duplicates = result.fetchall()
        print(f"找到 {len(duplicates)} 个有重复embedding的source_item")
        if duplicates:
            for row in duplicates:
                print(f"  source_item {row[0]}: {row[1]} 个embedding")
        print()
        
        # 2. 删除旧的embedding，只保留最新的
        print("清理重复的embedding...")
        result = await session.execute(text("""
            DELETE FROM embeddings
            WHERE id IN (
                SELECT e1.id
                FROM embeddings e1
                INNER JOIN embeddings e2 ON e1.object_type = e2.object_type 
                    AND e1.object_id = e2.object_id 
                    AND e1.created_at < e2.created_at
                WHERE e1.object_type = 'source_item'
            );
        """))
        
        deleted_count = result.rowcount
        print(f"删除了 {deleted_count} 个旧的embedding记录")
        
        await session.commit()
        print()
        
        # 3. 验证结果
        print("验证结果...")
        result = await session.execute(text("""
            SELECT object_id, COUNT(*) as count
            FROM embeddings
            WHERE object_type = 'source_item'
            GROUP BY object_id
            HAVING COUNT(*) > 1;
        """))
        
        remaining = result.fetchall()
        if remaining:
            print(f"⚠️  仍有 {len(remaining)} 个source_item有重复embedding")
        else:
            print("✅ 所有source_item现在都只有一个embedding")
        
        # 4. 检查PM周期数据的embedding状态
        print()
        print("检查PM周期数据的embedding状态...")
        result = await session.execute(text("""
            SELECT COUNT(*) as total,
                   COUNT(embedding_id) as has_embedding
            FROM source_items
            WHERE period = '2025-11-07_PM'
                AND merge_status = 'pending_event_merge';
        """))
        
        row = result.fetchone()
        if row:
            print(f"PM周期数据: {row[0]} 条, 有embedding: {row[1]} 条")


if __name__ == "__main__":
    print("=" * 60)
    print("清理重复的embedding记录")
    print("=" * 60)
    asyncio.run(cleanup())
    print("=" * 60)
    print("完成")
    print("=" * 60)

