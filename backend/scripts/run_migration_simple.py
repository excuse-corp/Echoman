"""
简化的数据库迁移脚本
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import asyncio
from sqlalchemy import text
from app.core.database import get_async_session


async def run_migration():
    """执行迁移SQL"""
    
    # 手动定义SQL语句（避免解析问题）
    statements = [
        "ALTER TABLE topic_halfday_heat RENAME TO topic_period_heat",
        "COMMENT ON TABLE topic_period_heat IS '主题归并周期热度记录表'",
        "ALTER TABLE source_items RENAME COLUMN halfday_merge_group_id TO period_merge_group_id",
        "ALTER TABLE source_items RENAME COLUMN halfday_period TO period",
        "COMMENT ON COLUMN source_items.period_merge_group_id IS '归并组ID'",
        "COMMENT ON COLUMN source_items.period IS '归并时段（如2025-10-29_AM/PM/EVE）'",
        "COMMENT ON COLUMN source_items.occurrence_count IS '归并周期内出现次数'",
        "COMMENT ON COLUMN source_items.heat_normalized IS '归并周期内归一化热度（0-1）'",
        "ALTER INDEX idx_halfday_period_status RENAME TO idx_period_status",
        "UPDATE source_items SET merge_status = 'pending_event_merge' WHERE merge_status = 'pending_halfday_merge'",
    ]
    
    async_session = get_async_session()
    
    async with async_session() as session:
        try:
            print("=" * 60)
            print("开始执行数据库迁移...")
            print("=" * 60)
            
            for idx, stmt in enumerate(statements, 1):
                print(f"\n[{idx}/{len(statements)}] {stmt[:60]}...")
                
                try:
                    await session.execute(text(stmt))
                    await session.commit()
                    print("  ✅ 成功")
                except Exception as e:
                    error_msg = str(e)
                    if 'does not exist' in error_msg or 'already exists' in error_msg:
                        print(f"  ⚠️  已处理: {error_msg[:80]}")
                        await session.rollback()
                        # 继续执行
                    else:
                        print(f"  ❌ 失败: {error_msg[:100]}")
                        await session.rollback()
                        raise
            
            print("\n" + "=" * 60)
            print("✅ 数据库迁移完成！")
            print("=" * 60)
            
            # 验证迁移结果
            print("\n验证迁移结果...")
            
            # 检查新表是否存在
            result = await session.execute(text(
                "SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = 'topic_period_heat')"
            ))
            exists = result.scalar()
            print(f"  topic_period_heat 表: {'✅ 存在' if exists else '❌ 不存在'}")
            
            # 检查新字段是否存在
            result = await session.execute(text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name = 'source_items' AND column_name IN ('period', 'period_merge_group_id')"
            ))
            columns = [row[0] for row in result.fetchall()]
            print(f"  source_items.period: {'✅ 存在' if 'period' in columns else '❌ 不存在'}")
            print(f"  source_items.period_merge_group_id: {'✅ 存在' if 'period_merge_group_id' in columns else '❌ 不存在'}")
            
            return True
            
        except Exception as e:
            await session.rollback()
            print(f"\n❌ 迁移失败: {e}")
            import traceback
            traceback.print_exc()
            return False


if __name__ == "__main__":
    success = asyncio.run(run_migration())
    sys.exit(0 if success else 1)

