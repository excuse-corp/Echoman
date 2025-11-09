"""
修复没有nodes的Topic

问题：有些Topic在创建时没有正确保存TopicNodes，导致无法进行分类
解决方案：删除这些不完整的Topic
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import select, and_, delete
from app.core.database import get_async_session
from app.models import Topic, TopicNode, TopicPeriodHeat
from datetime import datetime


async def fix_topics_without_nodes():
    """修复没有nodes的Topic"""
    
    async_session = get_async_session()
    
    async with async_session() as db:
        try:
            # 1. 找出没有nodes的Topic
            today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
            
            # 获取所有今天的topic id
            stmt_all = select(Topic.id).where(
                Topic.created_at >= today
            )
            all_topic_ids = set((await db.execute(stmt_all)).scalars().all())
            
            # 获取有nodes的topic id
            stmt_with_nodes = select(TopicNode.topic_id).distinct()
            topic_ids_with_nodes = set((await db.execute(stmt_with_nodes)).scalars().all())
            
            # 找出没有nodes的topic id
            topic_ids_without_nodes = all_topic_ids - topic_ids_with_nodes
            
            if not topic_ids_without_nodes:
                print("✅ 没有找到缺少nodes的Topic。")
                return
            
            print(f"📊 找到 {len(topic_ids_without_nodes)} 个没有nodes的Topic")
            print(f"   这些Topic将被删除（因为没有关联的source_items数据）")
            
            # 2. 删除这些Topic的相关数据
            
            # 删除 TopicPeriodHeat
            stmt_delete_heat = delete(TopicPeriodHeat).where(
                TopicPeriodHeat.topic_id.in_(list(topic_ids_without_nodes))
            )
            result_heat = await db.execute(stmt_delete_heat)
            print(f"   删除TopicPeriodHeat: {result_heat.rowcount} 条")
            
            # 删除 Topic
            stmt_delete_topic = delete(Topic).where(
                Topic.id.in_(list(topic_ids_without_nodes))
            )
            result_topic = await db.execute(stmt_delete_topic)
            print(f"   删除Topic: {result_topic.rowcount} 条")
            
            await db.commit()
            
            print(f"\n✅ 清理完成！")
            print(f"   已删除 {len(topic_ids_without_nodes)} 个不完整的Topic")
            
        except Exception as e:
            print(f"❌ 错误: {e}")
            import traceback
            traceback.print_exc()
            await db.rollback()


if __name__ == "__main__":
    print("=" * 60)
    print("修复没有nodes的Topic")
    print("=" * 60)
    asyncio.run(fix_topics_without_nodes())

