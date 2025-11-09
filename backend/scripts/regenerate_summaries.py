#!/usr/bin/env python
"""
为缺失摘要和placeholder摘要的Topics批量重新生成真实摘要
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import select, and_, or_
from app.core.database import get_async_session
from app.models import Topic, Summary, TopicNode
from app.services.summary_service import SummaryService


async def regenerate_summaries(limit=None):
    """为缺失或placeholder摘要的Topics重新生成摘要
    
    Args:
        limit: 限制处理的Topic数量，None表示处理全部
    """
    
    async_session = get_async_session()
    summary_service = SummaryService()
    
    async with async_session() as db:
        print("=" * 70)
        print("批量重新生成Topic摘要")
        print("=" * 70)
        
        # 1. 查找需要重新生成摘要的Topics
        # (1) 没有摘要的Topic
        # (2) 有placeholder摘要的Topic
        
        # 先找出所有placeholder的topic_id
        placeholder_stmt = select(Summary.topic_id).where(
            Summary.method == 'placeholder'
        )
        placeholder_topic_ids = [row[0] for row in (await db.execute(placeholder_stmt)).all()]
        
        # 查找所有需要处理的Topics
        stmt = select(Topic).where(
            and_(
                Topic.status == 'active',
                or_(
                    Topic.summary_id.is_(None),  # 没有摘要
                    Topic.id.in_(placeholder_topic_ids)  # 或者是placeholder
                )
            )
        ).order_by(Topic.first_seen.desc())
        
        if limit:
            stmt = stmt.limit(limit)
        
        topics = (await db.execute(stmt)).scalars().all()
        
        if not topics:
            print("✅ 所有Topics都已有真实摘要")
            return
        
        print(f"📊 找到 {len(topics)} 个需要重新生成摘要的Topics")
        print()
        
        # 2. 批量生成摘要（串行处理，避免并发问题）
        success_count = 0
        failed_count = 0
        placeholder_count = 0
        
        for i, topic in enumerate(topics, 1):
            try:
                # 检查是否有节点
                node_stmt = select(TopicNode).where(
                    TopicNode.topic_id == topic.id
                ).limit(1)
                has_nodes = (await db.execute(node_stmt)).first() is not None
                
                if not has_nodes:
                    print(f"[{i}/{len(topics)}] ⏭️  跳过 Topic {topic.id} (无节点)")
                    continue
                
                print(f"[{i}/{len(topics)}] 处理 Topic {topic.id}: {topic.title_key[:50]}...")
                
                # 删除旧的placeholder摘要（如果存在）
                if topic.id in placeholder_topic_ids:
                    delete_stmt = select(Summary).where(
                        and_(
                            Summary.topic_id == topic.id,
                            Summary.method == 'placeholder'
                        )
                    )
                    old_summary = (await db.execute(delete_stmt)).scalar_one_or_none()
                    if old_summary:
                        await db.delete(old_summary)
                        await db.commit()
                        print(f"  🗑️  已删除旧placeholder")
                
                # 生成新摘要
                summary = await summary_service.generate_full_summary(db, topic)
                
                if summary and summary.method == "full":
                    # 更新Topic的summary_id
                    topic.summary_id = summary.id
                    await db.commit()
                    success_count += 1
                    print(f"  ✅ 成功生成真实摘要 (Summary {summary.id})")
                elif summary and summary.method == "placeholder":
                    placeholder_count += 1
                    print(f"  ⚠️  仍然是placeholder")
                else:
                    failed_count += 1
                    print(f"  ❌ 生成失败")
                
            except Exception as e:
                failed_count += 1
                print(f"  ❌ 异常: {e}")
                await db.rollback()
            
            # 每10个打印一次进度
            if i % 10 == 0:
                print(f"\n进度: {i}/{len(topics)} ({i/len(topics)*100:.1f}%)")
                print(f"当前统计 - 成功: {success_count}, 失败: {failed_count}, Placeholder: {placeholder_count}\n")
            
            # 延迟避免API限流
            if i % 5 == 0:
                await asyncio.sleep(1)
        
        print()
        print("=" * 70)
        print(f"✅ 批量生成完成")
        print(f"   成功: {success_count}个")
        print(f"   失败: {failed_count}个")
        print(f"   Placeholder: {placeholder_count}个")
        print("=" * 70)


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='批量重新生成Topic摘要')
    parser.add_argument('--limit', type=int, default=None, 
                        help='限制处理的Topic数量（默认全部）')
    args = parser.parse_args()
    
    asyncio.run(regenerate_summaries(limit=args.limit))

