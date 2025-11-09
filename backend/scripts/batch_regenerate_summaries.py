#!/usr/bin/env python
"""
批量重新生成Topic摘要（不清理，直接生成）
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import select
from app.core.database import get_async_session
from app.models import Topic
from app.services.summary_service import SummaryService


async def batch_regenerate():
    """批量重新生成摘要"""
    print("=" * 70)
    print("批量重新生成Topic摘要和向量")
    print("=" * 70)
    print()
    
    async_session = get_async_session()
    summary_service = SummaryService()
    
    async with async_session() as db:
        # 查找所有活跃Topics
        stmt = select(Topic).where(
            Topic.status == 'active'
        ).order_by(Topic.first_seen.desc())
        
        topics = (await db.execute(stmt)).scalars().all()
        
        if not topics:
            print("✅ 没有需要处理的Topics")
            return
        
        print(f"📊 找到 {len(topics)} 个活跃Topics")
        print()
        
        # 批量生成摘要
        success_count = 0
        failed_count = 0
        skipped_count = 0
        
        for i, topic in enumerate(topics, 1):
            try:
                print(f"[{i}/{len(topics)}] Topic {topic.id}: {topic.title_key[:60]}...")
                
                # 生成摘要
                summary = await summary_service.generate_full_summary(db, topic)
                
                if summary and summary.method == "full":
                    # 更新Topic的summary_id
                    topic.summary_id = summary.id
                    await db.commit()
                    success_count += 1
                    print(f"  ✅ 成功 (Summary {summary.id})")
                elif summary and summary.method == "placeholder":
                    skipped_count += 1
                    print(f"  ⚠️  Placeholder")
                else:
                    failed_count += 1
                    print(f"  ❌ 失败")
                
            except Exception as e:
                failed_count += 1
                print(f"  ❌ 异常: {str(e)[:80]}")
                await db.rollback()
            
            # 每10个打印进度
            if i % 10 == 0:
                progress = i / len(topics) * 100
                print(f"\n进度: {i}/{len(topics)} ({progress:.1f}%)")
                print(f"统计: 成功={success_count}, 失败={failed_count}, Placeholder={skipped_count}\n")
            
            # 避免API限流
            if i % 5 == 0:
                await asyncio.sleep(1)
        
        print()
        print("=" * 70)
        print("✅ 批量生成完成")
        print(f"   成功: {success_count}")
        print(f"   失败: {failed_count}")
        print(f"   Placeholder: {skipped_count}")
        print(f"   总计: {len(topics)}")
        print("=" * 70)


if __name__ == "__main__":
    asyncio.run(batch_regenerate())

