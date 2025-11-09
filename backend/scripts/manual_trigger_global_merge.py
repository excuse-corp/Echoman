"""
手动触发全局归并（阶段二）
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import asyncio
from datetime import datetime
from app.core.database import get_async_session
from app.services.global_merge import GlobalMergeService


async def run_global_merge(target_period: str = None):
    """运行全局归并"""
    
    # 计算period
    if target_period:
        period = target_period
    else:
        now = datetime.now()
        date_str = now.strftime("%Y-%m-%d")
        if now.hour < 14:
            period_type = "AM"
        elif now.hour < 20:
            period_type = "PM"
        else:
            period_type = "EVE"
        
        period = f"{date_str}_{period_type}"
    
    print("=" * 60)
    print(f"手动执行全局归并: {period}")
    print("=" * 60)
    print()
    
    async_session = get_async_session()
    
    async with async_session() as db:
        service = GlobalMergeService(db)
        
        print("【阶段二】全局归并")
        print("-" * 60)
        
        result = await service.run_global_merge(period)
        
        print(f"   ✅ 全局归并完成")
        print(f"   输入: {result.get('input_events', 0)} 个事件")
        print(f"   新增主题: {result.get('new_topics', 0)} 个")
        print(f"   更新主题: {result.get('updated_topics', 0)} 个")
        print()
    
    print("=" * 60)
    print("✅ 全局归并完成")
    print("=" * 60)


if __name__ == "__main__":
    import sys
    target_period = sys.argv[1] if len(sys.argv) > 1 else None
    asyncio.run(run_global_merge(target_period))

