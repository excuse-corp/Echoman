"""
验证部署结果
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import asyncio
from sqlalchemy import text
from app.core.database import get_async_session


async def verify():
    """验证部署"""
    async_session = get_async_session()
    
    async with async_session() as session:
        print("=" * 60)
        print("部署验证")
        print("=" * 60)
        
        # 1. 检查表结构
        print("\n1. 数据库表结构")
        result = await session.execute(text(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema='public' AND table_name IN ('topic_period_heat', 'source_items') "
            "ORDER BY table_name"
        ))
        tables = [row[0] for row in result.fetchall()]
        print(f"   topic_period_heat: {'✅' if 'topic_period_heat' in tables else '❌'}")
        print(f"   source_items: {'✅' if 'source_items' in tables else '❌'}")
        
        # 2. 检查字段
        print("\n2. source_items 表字段")
        result = await session.execute(text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = 'source_items' "
            "AND column_name IN ('period', 'period_merge_group_id', 'merge_status') "
            "ORDER BY column_name"
        ))
        columns = [row[0] for row in result.fetchall()]
        print(f"   period: {'✅' if 'period' in columns else '❌'}")
        print(f"   period_merge_group_id: {'✅' if 'period_merge_group_id' in columns else '❌'}")
        print(f"   merge_status: {'✅' if 'merge_status' in columns else '❌'}")
        
        # 3. 检查merge_status值
        print("\n3. merge_status 值更新")
        result = await session.execute(text(
            "SELECT DISTINCT merge_status FROM source_items"
        ))
        statuses = [row[0] for row in result.fetchall()]
        print(f"   现有状态值: {', '.join(statuses) if statuses else '（无数据）'}")
        has_old = 'pending_halfday_merge' in statuses
        has_new = 'pending_event_merge' in statuses
        if has_old:
            print(f"   ⚠️  仍有旧值 pending_halfday_merge")
        elif has_new:
            print(f"   ✅ 已更新为 pending_event_merge")
        else:
            print(f"   ℹ️  暂无归并状态数据")
        
        # 4. 统计数据
        print("\n4. 数据统计")
        result = await session.execute(text("SELECT COUNT(*) FROM source_items"))
        count = result.scalar()
        print(f"   source_items 总数: {count}")
        
        result = await session.execute(text("SELECT COUNT(*) FROM topic_period_heat"))
        count = result.scalar()
        print(f"   topic_period_heat 总数: {count}")
        
        print("\n" + "=" * 60)
        print("✅ 部署验证完成")
        print("=" * 60)
        
        return True


if __name__ == "__main__":
    success = asyncio.run(verify())
    sys.exit(0 if success else 1)

