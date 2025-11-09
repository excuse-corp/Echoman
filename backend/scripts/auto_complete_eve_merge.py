#!/usr/bin/env python
"""
自动完成EVE周期的整体归并
持续运行直到所有pending_global_merge的数据都被处理完毕
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import select, and_, func
from app.core.database import get_async_session
from app.models import SourceItem
from app.services.global_merge import GlobalMergeService


async def get_pending_count(period: str) -> int:
    """获取待处理的数据量"""
    async_session = get_async_session()
    async with async_session() as db:
        stmt = select(func.count(SourceItem.id)).where(
            and_(
                SourceItem.period == period,
                SourceItem.merge_status == 'pending_global_merge'
            )
        )
        count = (await db.execute(stmt)).scalar()
        return count


async def run_one_round(period: str) -> dict:
    """运行一轮归并"""
    async_session = get_async_session()
    async with async_session() as db:
        service = GlobalMergeService(db)
        result = await service.run_global_merge(period)
        return result


async def auto_complete_merge(period: str, max_rounds: int = 100):
    """自动完成归并，直到所有数据处理完毕"""
    print("=" * 70)
    print(f"自动完成 {period} 周期的整体归并")
    print("=" * 70)
    print()
    
    round_num = 0
    total_merged = 0
    total_new = 0
    
    while round_num < max_rounds:
        round_num += 1
        
        # 检查待处理数量
        pending_count = await get_pending_count(period)
        
        if pending_count == 0:
            print(f"\n✅ 全部完成！共处理 {round_num - 1} 轮")
            print(f"   总归并: {total_merged}个")
            print(f"   新建Topic: {total_new}个")
            break
        
        print(f"\n【第 {round_num} 轮】")
        print(f"  待处理: {pending_count}条")
        
        try:
            # 运行一轮归并
            result = await run_one_round(period)
            
            merge_count = result.get('merge_count', 0)
            new_count = result.get('new_count', 0)
            duration = result.get('duration_seconds', 0)
            
            total_merged += merge_count
            total_new += new_count
            
            print(f"  ✅ 归并: {merge_count}个, 新建: {new_count}个, 耗时: {duration:.1f}秒")
            
            # 如果这一轮没有处理任何数据，说明可能遇到问题，退出
            if merge_count == 0 and new_count == 0:
                print(f"\n⚠️  这一轮没有处理任何数据，可能存在问题")
                print(f"   剩余待处理: {pending_count}条")
                break
                
        except Exception as e:
            print(f"  ❌ 归并失败: {e}")
            import traceback
            traceback.print_exc()
            break
        
        # 短暂休息，避免过度占用资源
        await asyncio.sleep(2)
    
    if round_num >= max_rounds:
        print(f"\n⚠️  达到最大轮数限制 ({max_rounds}轮)")
        pending_count = await get_pending_count(period)
        print(f"   剩余待处理: {pending_count}条")
    
    print("\n" + "=" * 70)


if __name__ == "__main__":
    period = sys.argv[1] if len(sys.argv) > 1 else "2025-11-07_EVE"
    max_rounds = int(sys.argv[2]) if len(sys.argv) > 2 else 100
    
    asyncio.run(auto_complete_merge(period, max_rounds))

