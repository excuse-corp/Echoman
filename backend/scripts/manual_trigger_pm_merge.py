"""
手动触发PM周期的归并任务（补偿18点失败的归并）
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import asyncio
from app.core.database import get_async_session, reset_db_engine
from app.services.heat_normalization import HeatNormalizationService
from app.services.halfday_merge import EventMergeService
from app.services.global_merge import GlobalMergeService


async def manual_pm_merge():
    """手动执行PM周期归并"""
    reset_db_engine()
    async_session = get_async_session()
    
    async with async_session() as db:
        period = "2025-11-07_PM"
        
        print("=" * 60)
        print(f"手动执行PM周期归并: {period}")
        print("=" * 60)
        
        # 阶段一：新事件归并
        print("\n【阶段一】新事件归并")
        print("-" * 60)
        
        try:
            # 1. 热度归一化
            print("1. 热度归一化...")
            heat_service = HeatNormalizationService(db)
            heat_result = await heat_service.normalize_period_heat(period)
            print(f"   ✅ 热度归一化完成: {heat_result.get('total_items', 0)} 条数据")
            
            # 2. 新事件归并
            print("2. 新事件归并...")
            merge_service = EventMergeService(db)
            merge_result = await merge_service.run_event_merge(period)
            print(f"   ✅ 新事件归并完成")
            print(f"   输入: {merge_result.get('input_count', 0)} 条")
            print(f"   保留: {merge_result.get('kept_count', 0)} 条")
            print(f"   丢弃: {merge_result.get('dropped_count', 0)} 条")
            print(f"   分组: {merge_result.get('groups_count', 0)} 组")
            
        except Exception as e:
            print(f"   ❌ 阶段一失败: {e}")
            import traceback
            traceback.print_exc()
            return
        
        # 阶段二：全局归并
        print("\n【阶段二】全局归并")
        print("-" * 60)
        
        try:
            global_service = GlobalMergeService(db)
            global_result = await global_service.run_global_merge(period)
            print(f"   ✅ 全局归并完成")
            print(f"   输入: {global_result.get('input_events', 0)} 个事件")
            print(f"   新增主题: {global_result.get('new_topics', 0)} 个")
            print(f"   更新主题: {global_result.get('updated_topics', 0)} 个")
            
        except Exception as e:
            print(f"   ❌ 阶段二失败: {e}")
            import traceback
            traceback.print_exc()
            return
        
        print("\n" + "=" * 60)
        print("✅ PM周期归并完成")
        print("=" * 60)


if __name__ == "__main__":
    asyncio.run(manual_pm_merge())

