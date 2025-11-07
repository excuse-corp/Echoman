"""
修复 halfday_period 字段

为没有 halfday_period 的数据设置正确的半日时段标识
"""
import asyncio
import sys
import os
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.core.database import async_session
from app.models import SourceItem
from app.services.heat_normalization import HeatNormalizationService
from sqlalchemy import select


async def fix_halfday_period():
    """修复 halfday_period 字段"""
    async with async_session() as db:
        print("🔧 开始修复 halfday_period 字段...\n")
        
        # 查找所有没有 halfday_period 的数据
        stmt = select(SourceItem).where(
            SourceItem.halfday_period.is_(None)
        )
        result = await db.execute(stmt)
        items = result.scalars().all()
        
        print(f"📊 发现 {len(items)} 条数据没有 halfday_period")
        
        if not items:
            print("✅ 所有数据都已经有 halfday_period")
            return
        
        heat_service = HeatNormalizationService(db)
        
        # 统计按时间分组
        period_counts = {}
        
        for item in items:
            # 根据 fetched_at 计算半日时段
            if item.fetched_at:
                date_str = item.fetched_at.strftime("%Y-%m-%d")
                hour = item.fetched_at.hour
                period = "AM" if hour < 12 else "PM"
                halfday_period = f"{date_str}_{period}"
            else:
                # 如果没有 fetched_at，使用当前时间
                halfday_period = heat_service.calculate_halfday_period()
            
            item.halfday_period = halfday_period
            
            period_counts[halfday_period] = period_counts.get(halfday_period, 0) + 1
        
        await db.commit()
        
        print(f"\n✅ 修复完成！更新了 {len(items)} 条数据")
        print(f"\n📅 数据分布:")
        for period, count in sorted(period_counts.items()):
            print(f"  - {period}: {count} 条")


if __name__ == "__main__":
    asyncio.run(fix_halfday_period())

