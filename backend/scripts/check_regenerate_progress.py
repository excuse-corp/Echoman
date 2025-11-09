#!/usr/bin/env python
"""
检查摘要重新生成的进度
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import select, func
from app.core.database import get_async_session
from app.models import Topic, Summary


async def check_progress():
    """检查生成进度"""
    async_session = get_async_session()
    async with async_session() as db:
        # 统计Topic总数
        total_topics = (await db.execute(
            select(func.count(Topic.id)).where(Topic.status == 'active')
        )).scalar()
        
        # 统计已有摘要的Topic
        topics_with_summary = (await db.execute(
            select(func.count(Topic.id)).where(
                Topic.status == 'active',
                Topic.summary_id.isnot(None)
            )
        )).scalar()
        
        # 统计Summary数量和方法分布
        summary_count = (await db.execute(
            select(func.count(Summary.id))
        )).scalar()
        
        method_stats = (await db.execute(
            select(Summary.method, func.count(Summary.id))
            .group_by(Summary.method)
        )).all()
        
        # 统计向量数量
        from app.models import Embedding
        embedding_count = (await db.execute(
            select(func.count(Embedding.id))
            .where(Embedding.object_type == 'topic_summary')
        )).scalar()
        
        # 打印统计信息
        print("=" * 70)
        print("摘要重新生成进度")
        print("=" * 70)
        print(f"\n📊 Topic统计:")
        print(f"   活跃Topic总数: {total_topics}")
        print(f"   已有摘要: {topics_with_summary} ({topics_with_summary/total_topics*100:.1f}%)")
        print(f"   缺少摘要: {total_topics - topics_with_summary} ({(total_topics - topics_with_summary)/total_topics*100:.1f}%)")
        
        print(f"\n📝 Summary统计:")
        print(f"   总数: {summary_count}")
        for method, count in method_stats:
            print(f"   {method}: {count}个")
        
        print(f"\n🔢 向量统计:")
        print(f"   topic_summary向量数: {embedding_count}")
        
        print(f"\n📈 进度:")
        if total_topics > 0:
            progress = topics_with_summary / total_topics * 100
            bar_length = 50
            filled = int(bar_length * topics_with_summary / total_topics)
            bar = '█' * filled + '░' * (bar_length - filled)
            print(f"   [{bar}] {progress:.1f}%")
        
        print("\n" + "=" * 70)


if __name__ == "__main__":
    asyncio.run(check_progress())

