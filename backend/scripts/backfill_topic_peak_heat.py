"""
回填 Topic 峰值热度（current_heat_normalized / heat_percentage）
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import select, func
from app.core.database import get_async_session
from app.models import Topic, TopicPeriodHeat


async def backfill_topic_peak_heat():
    async_session = get_async_session()

    async with async_session() as db:
        try:
            # 统计每个 Topic 的历史峰值热度
            stmt = (
                select(
                    TopicPeriodHeat.topic_id,
                    func.max(TopicPeriodHeat.heat_normalized).label("max_heat"),
                )
                .group_by(TopicPeriodHeat.topic_id)
            )
            result = await db.execute(stmt)
            rows = result.all()

            if not rows:
                print("✅ 没有找到任何 TopicPeriodHeat 记录。")
                return

            max_map = {row.topic_id: (row.max_heat or 0.0) for row in rows}
            topic_ids = list(max_map.keys())

            # 读取 Topic 并更新峰值
            stmt = select(Topic).where(Topic.id.in_(topic_ids))
            result = await db.execute(stmt)
            topics = result.scalars().all()

            updated = 0
            for topic in topics:
                peak = max_map.get(topic.id, 0.0)
                if topic.current_heat_normalized != peak:
                    topic.current_heat_normalized = peak
                    topic.heat_percentage = peak * 100
                    updated += 1

            await db.commit()

            print(f"✅ 回填完成：共{len(topic_ids)}个Topic，有{updated}个更新为峰值热度。")
        except Exception as e:
            print(f"❌ 回填失败: {e}")
            import traceback
            traceback.print_exc()
            await db.rollback()


if __name__ == "__main__":
    print("=" * 60)
    print("回填 Topic 峰值热度")
    print("=" * 60)
    asyncio.run(backfill_topic_peak_heat())
