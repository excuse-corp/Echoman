#!/usr/bin/env python
"""
展示已生成摘要的Topics
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import select
from app.core.database import get_async_session
from app.models import Topic, Summary, Embedding


async def show_completed_topics():
    """展示已生成摘要的Topics"""
    async_session = get_async_session()
    async with async_session() as db:
        # 查询已有摘要的Topics
        stmt = select(Topic, Summary).join(
            Summary, Topic.summary_id == Summary.id
        ).where(
            Topic.status == 'active',
            Summary.method == 'full'
        ).order_by(Topic.id)
        
        results = (await db.execute(stmt)).all()
        
        print('=' * 100)
        print(f'已生成真实摘要的Topics ({len(results)}个)')
        print('=' * 100)
        print()
        
        for i, (topic, summary) in enumerate(results, 1):
            # 检查是否有向量
            stmt = select(Embedding.id).where(
                Embedding.object_type == 'topic_summary',
                Embedding.object_id == summary.id
            )
            embedding_id = (await db.execute(stmt)).scalar_one_or_none()
            
            print(f'【{i}】Topic {topic.id}')
            print(f'标题: {topic.title_key}')
            print(f'首次发现: {topic.first_seen.strftime("%Y-%m-%d %H:%M")}')
            print(f'最后活跃: {topic.last_active.strftime("%Y-%m-%d %H:%M")}')
            
            if topic.category:
                print(f'分类: {topic.category} (置信度: {topic.category_confidence:.2f})')
            else:
                print('分类: 未分类')
            print()
            
            print(f'Summary {summary.id}:')
            print(f'生成时间: {summary.generated_at.strftime("%Y-%m-%d %H:%M:%S")}')
            print(f'LLM模型: {summary.provider}/{summary.model}')
            
            # 显示摘要内容（截断）
            if len(summary.content) > 200:
                print(f'摘要内容: {summary.content[:200]}...')
            else:
                print(f'摘要内容: {summary.content}')
            print()
            
            # 显示向量状态
            if embedding_id:
                print(f'向量: ✅ 已生成 (Embedding {embedding_id})')
            else:
                print('向量: ❌ 缺失')
            
            print('-' * 100)
            print()


if __name__ == "__main__":
    asyncio.run(show_completed_topics())

