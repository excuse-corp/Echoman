"""
检查指定run_id的采集结果
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import asyncio
from sqlalchemy import text
from app.core.database import get_async_session


async def check_run(run_id):
    """检查采集结果"""
    async_session = get_async_session()
    
    async with async_session() as session:
        print("=" * 60)
        print(f"采集运行检查: {run_id}")
        print("=" * 60)
        
        # 1. 检查运行记录
        print("\n1. 运行记录:")
        result = await session.execute(text("""
            SELECT 
                run_id,
                status,
                started_at,
                ended_at,
                duration_ms,
                total_platforms,
                success_platforms,
                failed_platforms,
                total_items,
                success_items,
                failed_items
            FROM runs_ingest 
            WHERE run_id = :run_id;
        """), {"run_id": run_id})
        
        row = result.fetchone()
        if row:
            print(f"  状态: {row[1]}")
            print(f"  开始: {row[2]}")
            print(f"  结束: {row[3]}")
            print(f"  耗时: {row[4]}ms ({row[4]/1000:.1f}秒)")
            print(f"  平台: 成功{row[6]}/{row[5]}, 失败{row[7]}")
            print(f"  数据: 采集{row[8]}条, 成功{row[9]}条, 失败{row[10]}条")
            status = row[1]
        else:
            print("  ❌ 未找到运行记录（可能还在执行中）")
            return
        
        # 2. 如果完成，检查采集的数据
        if status == "success":
            print("\n2. 采集数据统计:")
            result = await session.execute(text("""
                SELECT 
                    platform,
                    period,
                    merge_status,
                    COUNT(*) as count
                FROM source_items 
                WHERE run_id = :run_id
                GROUP BY platform, period, merge_status
                ORDER BY platform, period;
            """), {"run_id": run_id})
            
            rows = result.fetchall()
            if rows:
                for row in rows:
                    print(f"  {row[0]:10} | {row[1]:20} | {row[2]:25} | {row[3]:3}条")
            else:
                print("  （无数据）")
            
            # 3. 总计
            print("\n3. 总计:")
            result = await session.execute(text("""
                SELECT 
                    COUNT(*) as total,
                    COUNT(DISTINCT platform) as platforms,
                    COUNT(DISTINCT period) as periods
                FROM source_items 
                WHERE run_id = :run_id;
            """), {"run_id": run_id})
            
            row = result.fetchone()
            if row:
                print(f"  总数据: {row[0]} 条")
                print(f"  平台数: {row[1]} 个")
                print(f"  周期: {row[2]} 个")
                
                # 显示具体周期
                result = await session.execute(text("""
                    SELECT DISTINCT period FROM source_items WHERE run_id = :run_id;
                """), {"run_id": run_id})
                periods = [r[0] for r in result.fetchall()]
                print(f"  周期列表: {', '.join(periods)}")


if __name__ == "__main__":
    run_id = sys.argv[1] if len(sys.argv) > 1 else "run_4daac2c0f96f"
    asyncio.run(check_run(run_id))

