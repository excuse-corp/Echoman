"""
诊断pending_global_merge数据为什么没有被处理
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import asyncio
from sqlalchemy import text
from app.core.database import get_async_session


async def diagnose():
    """诊断"""
    async_session = get_async_session()
    
    async with async_session() as session:
        print("诊断pending_global_merge数据...")
        print()
        
        # 1. 检查pending_global_merge的分布
        print("【1. 归并组分布】")
        result = await session.execute(text("""
            SELECT period_merge_group_id, 
                   COUNT(*) as item_count,
                   MIN(title) as sample_title
            FROM source_items
            WHERE period = '2025-11-07_PM'
                AND merge_status = 'pending_global_merge'
            GROUP BY period_merge_group_id
            ORDER BY item_count DESC
            LIMIT 10;
        """))
        
        print("前10个归并组:")
        for row in result:
            print(f"  组ID: {row[0]:40s} | 数量: {row[1]:2d} | 示例: {row[2][:50]}")
        print()
        
        # 2. 检查是否有embedding问题
        print("【2. Embedding状态】")
        result = await session.execute(text("""
            SELECT COUNT(*) as total,
                   COUNT(embedding_id) as has_embedding
            FROM source_items
            WHERE period = '2025-11-07_PM'
                AND merge_status = 'pending_global_merge';
        """))
        row = result.fetchone()
        print(f"总数: {row[0]}, 有embedding: {row[1]}")
        print()
        
        # 3. 检查LLM判断记录
        print("【3. LLM判断记录】")
        result = await session.execute(text("""
            SELECT status, COUNT(*) as count
            FROM llm_judgements
            WHERE type = 'global_merge'
                AND created_at >= '2025-11-07 18:00:00'
            GROUP BY status;
        """))
        print("判断状态分布:")
        for row in result:
            print(f"  {row[0]}: {row[1]} 条")
        print()
        
        # 4. 检查失败的LLM判断
        print("【4. 失败的LLM判断】")
        result = await session.execute(text("""
            SELECT error_message, COUNT(*) as count
            FROM llm_judgements
            WHERE type = 'global_merge'
                AND created_at >= '2025-11-07 18:00:00'
                AND status != 'success'
            GROUP BY error_message
            LIMIT 5;
        """))
        errors = result.fetchall()
        if errors:
            print("错误类型:")
            for row in errors:
                print(f"  {row[0][:100]}: {row[1]} 条")
        else:
            print("  无失败记录")
        print()
        
        # 5. 检查是否有pending数据对应的LLM判断
        print("【5. 未判断的归并组】")
        result = await session.execute(text("""
            WITH pending_groups AS (
                SELECT DISTINCT period_merge_group_id
                FROM source_items
                WHERE period = '2025-11-07_PM'
                    AND merge_status = 'pending_global_merge'
            ),
            judged_items AS (
                SELECT DISTINCT (request->>'item_id')::bigint as item_id
                FROM llm_judgements
                WHERE type = 'global_merge'
                    AND created_at >= '2025-11-07 18:00:00'
            )
            SELECT COUNT(DISTINCT si.period_merge_group_id) as unjudged_groups,
                   COUNT(DISTINCT si.id) as unjudged_items
            FROM source_items si
            WHERE si.period = '2025-11-07_PM'
                AND si.merge_status = 'pending_global_merge'
                AND si.id NOT IN (SELECT item_id FROM judged_items WHERE item_id IS NOT NULL);
        """))
        row = result.fetchone()
        print(f"未判断的归并组: {row[0]} 个")
        print(f"未判断的数据项: {row[1]} 条")
        print()
        
        # 6. 检查run记录
        print("【6. Run记录】")
        result = await session.execute(text("""
            SELECT stage, status, COUNT(*) as count,
                   MAX(created_at) as last_run
            FROM runs_pipeline
            WHERE stage IN ('event_merge', 'global_merge')
                AND created_at >= '2025-11-07 18:00:00'
            GROUP BY stage, status
            ORDER BY stage, status;
        """))
        print("Run记录:")
        for row in result:
            print(f"  {row[0]:15s} | {row[1]:10s} | {row[2]:3d} 次 | 最后: {row[3]}")


if __name__ == "__main__":
    asyncio.run(diagnose())

