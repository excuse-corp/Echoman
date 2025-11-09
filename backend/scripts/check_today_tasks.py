"""
检查今天的采集任务情况
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import asyncio
from sqlalchemy import text
from app.core.database import get_async_session


async def check_today_tasks():
    async_session = get_async_session()
    async with async_session() as db:
        print('=' * 120)
        print('今天（2025-11-08）的采集任务情况')
        print('=' * 120)
        
        # 1. 查询今天的采集任务记录
        result = await db.execute(
            text('''
                SELECT 
                    run_id,
                    to_char(started_at AT TIME ZONE 'Asia/Shanghai', 'HH24:MI:SS') as start_time,
                    to_char(ended_at AT TIME ZONE 'Asia/Shanghai', 'HH24:MI:SS') as end_time,
                    status,
                    total_items,
                    success_items,
                    duration_ms
                FROM runs_ingest
                WHERE date_trunc('day', started_at AT TIME ZONE 'Asia/Shanghai') = '2025-11-08'
                ORDER BY started_at
            ''')
        )
        runs = result.all()
        
        print(f'\n📊 采集任务记录（共 {len(runs)} 次）:')
        print('-' * 120)
        if runs:
            for run in runs:
                status_icon = '✅' if run[3] == 'success' else '❌' if run[3] == 'failed' else '⏳'
                duration_sec = run[6] / 1000 if run[6] else 0
                print(f'{status_icon} {run[0]} | 开始: {run[1]} | 结束: {run[2]} | '
                      f'状态: {run[3]:10s} | 总数: {run[4]:4d} | 成功: {run[5]:4d} | 耗时: {duration_sec:.1f}秒')
        else:
            print('   ⚠️  今天还没有采集任务记录')
        
        # 2. 统计今天采集的source_items
        result = await db.execute(
            text('''
                SELECT 
                    period,
                    COUNT(*) as count,
                    COUNT(DISTINCT platform) as platform_count
                FROM source_items
                WHERE date_trunc('day', fetched_at AT TIME ZONE 'Asia/Shanghai') = '2025-11-08'
                GROUP BY period
                ORDER BY 
                    CASE period
                        WHEN 'AM' THEN 1
                        WHEN 'PM' THEN 2
                        WHEN 'EVE' THEN 3
                    END
            ''')
        )
        items_by_period = result.all()
        
        print(f'\n📦 采集数据统计（按时段）:')
        print('-' * 120)
        if items_by_period:
            total_items = 0
            for period_data in items_by_period:
                period, count, platform_count = period_data
                total_items += count
                print(f'   {period:3s} 时段: {count:4d} 条数据，来自 {platform_count} 个平台')
            
            print(f'\n   总计: {total_items} 条数据')
        else:
            print('   ⚠️  今天还没有采集到数据')
        
        # 3. 统计每个平台的采集情况
        result = await db.execute(
            text('''
                SELECT 
                    platform,
                    COUNT(*) as count
                FROM source_items
                WHERE date_trunc('day', fetched_at AT TIME ZONE 'Asia/Shanghai') = '2025-11-08'
                GROUP BY platform
                ORDER BY count DESC
            ''')
        )
        items_by_platform = result.all()
        
        if items_by_platform:
            print(f'\n📱 各平台采集统计:')
            print('-' * 120)
            for platform, count in items_by_platform:
                print(f'   {platform:15s}: {count:4d} 条')
        
        # 4. 检查归并状态
        result = await db.execute(
            text('''
                SELECT 
                    merge_status,
                    COUNT(*) as count
                FROM source_items
                WHERE date_trunc('day', fetched_at AT TIME ZONE 'Asia/Shanghai') = '2025-11-08'
                GROUP BY merge_status
                ORDER BY count DESC
            ''')
        )
        merge_status = result.all()
        
        if merge_status:
            print(f'\n🔄 归并状态统计:')
            print('-' * 120)
            for status, count in merge_status:
                print(f'   {status:25s}: {count:4d} 条')
        
        # 5. 检查今天的归并任务
        result = await db.execute(
            text('''
                SELECT 
                    stage,
                    to_char(started_at AT TIME ZONE 'Asia/Shanghai', 'HH24:MI:SS') as start_time,
                    status,
                    items_processed,
                    duration_seconds
                FROM runs_pipeline
                WHERE date_trunc('day', started_at AT TIME ZONE 'Asia/Shanghai') = '2025-11-08'
                ORDER BY started_at
            ''')
        )
        merge_runs = result.all()
        
        print(f'\n🔗 归并任务记录（共 {len(merge_runs)} 次）:')
        print('-' * 120)
        if merge_runs:
            for run in merge_runs:
                status_icon = '✅' if run[2] == 'completed' else '❌' if run[2] == 'failed' else '⏳'
                print(f'{status_icon} {run[0]:15s} | 开始: {run[1]} | 状态: {run[2]:10s} | '
                      f'处理: {run[3] or 0:4d} 条 | 耗时: {run[4] or 0:.1f}秒')
        else:
            print('   ⚠️  今天还没有归并任务记录')
        
        print('\n' + '=' * 120)


if __name__ == "__main__":
    asyncio.run(check_today_tasks())

