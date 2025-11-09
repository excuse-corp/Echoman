"""
手动对未分类的Topic进行分类
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import select, and_, or_
from app.core.database import get_async_session
from app.models import Topic
from app.services.classification_service import ClassificationService
from app.utils.timezone import now_cn
from datetime import datetime


async def classify_unclassified_topics():
    """对未分类的Topic进行分类"""
    
    async_session = get_async_session()
    
    async with async_session() as db:
        try:
            # 获取未分类的Topic
            today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
            stmt = select(Topic).where(
                and_(
                    Topic.created_at >= today,
                    Topic.status == "active",
                    or_(
                        Topic.category.is_(None),
                        Topic.category == ""
                    )
                )
            ).order_by(
                Topic.created_at.desc()
            )
            result = await db.execute(stmt)
            unclassified_topics = result.scalars().all()
            
            if not unclassified_topics:
                print("✅ 没有找到未分类的Topic。")
                return
            
            print(f"📊 找到 {len(unclassified_topics)} 个未分类的Topic")
            print("🔄 开始分类...")
            
            # 初始化分类服务
            classification_service = ClassificationService()
            
            success_count = 0
            fail_count = 0
            
            for topic in unclassified_topics:
                try:
                    print(f"\n处理 Topic {topic.id}: {topic.title_key[:50]}...")
                    
                    # 执行分类
                    category, confidence, method = await classification_service.classify_topic(
                        db, topic, force_llm=False
                    )
                    
                    # 更新Topic
                    topic.category = category
                    topic.category_confidence = confidence
                    topic.category_method = method
                    topic.category_updated_at = now_cn()
                    
                    await db.commit()
                    
                    print(f"  ✅ 分类完成: {category} (置信度: {confidence:.2f}, 方法: {method})")
                    success_count += 1
                    
                except Exception as e:
                    print(f"  ❌ 分类失败: {e}")
                    fail_count += 1
                    await db.rollback()
                    import traceback
                    traceback.print_exc()
            
            print(f"\n{'='*60}")
            print(f"分类完成！")
            print(f"  成功: {success_count}")
            print(f"  失败: {fail_count}")
            print(f"{'='*60}")
            
        except Exception as e:
            print(f"❌ 错误: {e}")
            import traceback
            traceback.print_exc()
            await db.rollback()


if __name__ == "__main__":
    print("=" * 60)
    print("手动对未分类的Topic进行分类")
    print("=" * 60)
    asyncio.run(classify_unclassified_topics())

