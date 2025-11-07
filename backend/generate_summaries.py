#!/usr/bin/env python3
"""为所有没有摘要的Topics批量生成摘要"""
import asyncio
import sys
from sqlalchemy import select
from app.core.database import AsyncSessionLocal
from app.models import Topic
from app.services.summary_service import SummaryService
from app.services.classification_service import ClassificationService
from app.utils.timezone import now_cn

async def generate_missing_summaries():
    """为所有没有摘要的Topics生成摘要"""
    async with AsyncSessionLocal() as db:
        # 查询所有没有摘要的Topics
        stmt = select(Topic).where(
            Topic.summary_id.is_(None),
            Topic.status == "active"
        ).order_by(Topic.id)
        
        result = await db.execute(stmt)
        topics = result.scalars().all()
        
        print(f"📊 找到 {len(topics)} 个需要生成摘要的Topics")
        
        if not topics:
            print("✅ 所有Topics都已有摘要")
            return
        
        summary_service = SummaryService()
        classification_service = ClassificationService()
        
        success_count = 0
        failed_count = 0
        
        for i, topic in enumerate(topics, 1):
            print(f"\n[{i}/{len(topics)}] 处理 Topic {topic.id}: {topic.title_key}")
            
            try:
                # 1. 生成分类（如果还没有）
                if not topic.category:
                    print(f"  🏷️  生成分类...")
                    category, confidence, method = await classification_service.classify_topic(
                        db, topic, force_llm=False
                    )
                    topic.category = category
                    topic.category_confidence = confidence
                    topic.category_method = method
                    topic.category_updated_at = now_cn()
                    print(f"  ✅ 分类: {category} (置信度: {confidence:.2f})")
                
                # 2. 生成摘要
                print(f"  📝 生成摘要...")
                summary = await summary_service.generate_full_summary(db, topic)
                
                await db.commit()
                
                print(f"  ✅ 摘要生成成功 (ID: {summary.id})")
                success_count += 1
                
            except Exception as e:
                print(f"  ❌ 失败: {e}")
                failed_count += 1
                import traceback
                traceback.print_exc()
                await db.rollback()
        
        print(f"\n{'='*60}")
        print(f"📊 批量生成完成:")
        print(f"  ✅ 成功: {success_count} 个")
        print(f"  ❌ 失败: {failed_count} 个")
        print(f"{'='*60}")

if __name__ == "__main__":
    asyncio.run(generate_missing_summaries())

