"""
针对特定的Topic重新生成摘要

这些Topic的摘要被截断或损坏，需要重新调用LLM生成
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import asyncio
from sqlalchemy import select
from app.core.database import get_async_session
from app.models.topic import Topic
from app.models.summary import Summary
from app.services.summary_service import SummaryService


async def regenerate_summaries(topic_ids: list[int]):
    """重新生成指定Topic的摘要"""
    async_session = get_async_session()
    async with async_session() as db:
        summary_service = SummaryService()
        
        print("=" * 120)
        print(f"重新生成 {len(topic_ids)} 个Topic的摘要")
        print("=" * 120)
        
        success_count = 0
        failed_count = 0
        
        for i, topic_id in enumerate(topic_ids, 1):
            print(f"\n【{i}/{len(topic_ids)}】处理 Topic {topic_id}")
            print("-" * 120)
            
            # 查询Topic
            result = await db.execute(
                select(Topic).where(Topic.id == topic_id)
            )
            topic = result.scalar_one_or_none()
            
            if not topic:
                print(f"❌ Topic {topic_id} 不存在")
                failed_count += 1
                continue
            
            print(f"   标题: {topic.title_key}")
            print(f"   分类: {topic.category}")
            print(f"   首次发现: {topic.first_seen}")
            print(f"   最后活跃: {topic.last_active}")
            
            # 删除旧摘要
            if topic.summary_id:
                print(f"   🗑️  删除旧摘要 (Summary ID: {topic.summary_id})")
                old_summary = await db.get(Summary, topic.summary_id)
                if old_summary:
                    await db.delete(old_summary)
                    await db.commit()
                
                topic.summary_id = None
                await db.commit()
            
            try:
                # 生成新摘要
                print(f"   🤖 调用LLM生成新摘要...")
                new_summary = await summary_service.generate_full_summary(db, topic)
                
                if new_summary and new_summary.content:
                    print(f"   ✅ 摘要生成成功 (Summary ID: {new_summary.id})")
                    print(f"   📏 摘要长度: {len(new_summary.content)} 字符")
                    print(f"   📝 摘要预览: {new_summary.content[:200]}...")
                    success_count += 1
                else:
                    print(f"   ❌ 摘要生成失败（返回None或空内容）")
                    failed_count += 1
                    
            except Exception as e:
                print(f"   ❌ 摘要生成失败: {e}")
                import traceback
                print(f"   完整堆栈:\n{traceback.format_exc()}")
                failed_count += 1
        
        print("\n" + "=" * 120)
        print(f"重新生成完成")
        print(f"   ✅ 成功: {success_count} 个")
        print(f"   ❌ 失败: {failed_count} 个")
        print("=" * 120)


async def main():
    # 需要重新生成摘要的Topic ID列表（来自损坏的摘要）
    topic_ids = [
        433,  # Summary 293: 中国抓拍到的星际来客到底什么来头
        387,  # Summary 338: 惨不忍睹！快船惨遭三连败
        265,  # Summary 394: 在冰箱冷藏一夜的蛋糕
        84,   # Summary 539: 患癌男子8万救命钱全打赏主播
        76,   # Summary 550: 学生买淀粉肠被拔车钥匙 校方再通报
    ]
    
    await regenerate_summaries(topic_ids)


if __name__ == "__main__":
    asyncio.run(main())

