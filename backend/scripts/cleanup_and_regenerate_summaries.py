#!/usr/bin/env python
"""
完整的摘要清理与重新生成脚本
1. 清理PostgreSQL中的旧摘要和向量数据
2. 清理ChromaDB中的topic_summary向量
3. 为所有活跃Topic重新生成摘要和向量
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import select, delete, and_
from app.core.database import get_async_session
from app.models import Topic, Summary, Embedding
from app.services.summary_service import SummaryService
from app.services.vector_service import get_vector_service


async def cleanup_old_data():
    """清理旧的摘要和向量数据"""
    print("=" * 70)
    print("第1步：清理旧数据")
    print("=" * 70)
    
    async_session = get_async_session()
    async with async_session() as db:
        # 1. 统计待清理数据
        from sqlalchemy import func
        summary_count = (await db.execute(select(func.count(Summary.id)))).scalar()
        topic_summary_embedding_count = (await db.execute(
            select(func.count(Embedding.id)).where(Embedding.object_type == 'topic_summary')
        )).scalar()
        
        print(f"\n📊 待清理数据统计:")
        print(f"   Summary记录: {summary_count}个")
        print(f"   topic_summary Embedding记录: {topic_summary_embedding_count}个")
        
        # 2. 清理PostgreSQL中的topic_summary向量
        if topic_summary_embedding_count > 0:
            print(f"\n🗑️  清理PostgreSQL中的topic_summary向量...")
            stmt = delete(Embedding).where(Embedding.object_type == 'topic_summary')
            await db.execute(stmt)
            await db.commit()
            print(f"   ✅ 已删除 {topic_summary_embedding_count} 个向量记录")
        
        # 3. 清理所有Summary
        if summary_count > 0:
            print(f"\n🗑️  清理所有Summary...")
            stmt = delete(Summary)
            await db.execute(stmt)
            await db.commit()
            print(f"   ✅ 已删除 {summary_count} 个Summary记录")
        
        # 4. 清理Topic的summary_id关联
        print(f"\n🔗 重置Topic的summary_id...")
        stmt = select(Topic).where(
            Topic.status == 'active',
            Topic.summary_id.isnot(None)
        )
        topics = (await db.execute(stmt)).scalars().all()
        
        for topic in topics:
            topic.summary_id = None
        
        if topics:
            await db.commit()
            print(f"   ✅ 已重置 {len(topics)} 个Topic的summary_id")
    
    # 5. 清理ChromaDB中的topic_summary向量
    print(f"\n🗑️  清理ChromaDB中的topic_summary向量...")
    try:
        vector_service = get_vector_service()
        if vector_service.db_type == "chroma":
            # 获取所有topic_summary类型的向量ID
            collection = vector_service.collection
            results = collection.get(
                where={"object_type": "topic_summary"}
            )
            
            if results and results['ids']:
                chroma_count = len(results['ids'])
                print(f"   找到 {chroma_count} 个topic_summary向量")
                
                # 批量删除
                collection.delete(
                    ids=results['ids']
                )
                print(f"   ✅ 已从ChromaDB删除 {chroma_count} 个向量")
            else:
                print(f"   ℹ️  ChromaDB中没有topic_summary向量")
        else:
            print(f"   ℹ️  当前使用的不是ChromaDB，跳过")
    except Exception as e:
        print(f"   ⚠️  ChromaDB清理失败: {e}")
    
    print("\n" + "=" * 70)
    print("✅ 旧数据清理完成")
    print("=" * 70)
    print()


async def regenerate_all_summaries():
    """为所有活跃Topic重新生成摘要"""
    print("=" * 70)
    print("第2步：批量重新生成摘要和向量")
    print("=" * 70)
    
    async_session = get_async_session()
    summary_service = SummaryService()
    
    async with async_session() as db:
        # 查找所有活跃且有节点的Topics
        stmt = select(Topic).where(
            Topic.status == 'active'
        ).order_by(Topic.first_seen.desc())
        
        topics = (await db.execute(stmt)).scalars().all()
        
        if not topics:
            print("✅ 没有需要处理的Topics")
            return
        
        print(f"📊 找到 {len(topics)} 个活跃Topics\n")
        
        # 批量生成摘要
        success_count = 0
        failed_count = 0
        skipped_count = 0
        
        for i, topic in enumerate(topics, 1):
            try:
                print(f"[{i}/{len(topics)}] 处理 Topic {topic.id}: {topic.title_key[:60]}...")
                
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
                    print(f"  ⚠️  Placeholder (可能无节点或生成失败)")
                else:
                    failed_count += 1
                    print(f"  ❌ 失败")
                
            except Exception as e:
                failed_count += 1
                print(f"  ❌ 异常: {str(e)[:100]}")
                await db.rollback()
            
            # 每10个打印一次进度
            if i % 10 == 0:
                print(f"\n进度: {i}/{len(topics)} ({i/len(topics)*100:.1f}%)")
                print(f"当前统计 - 成功: {success_count}, 失败: {failed_count}, Placeholder: {skipped_count}\n")
            
            # 延迟避免API限流（每5个暂停1秒）
            if i % 5 == 0:
                await asyncio.sleep(1)
        
        print()
        print("=" * 70)
        print(f"✅ 批量生成完成")
        print(f"   成功: {success_count}个")
        print(f"   失败: {failed_count}个")
        print(f"   Placeholder: {skipped_count}个")
        print(f"   总计: {len(topics)}个")
        print("=" * 70)


async def main():
    """主函数"""
    print("\n" + "=" * 70)
    print("完整的摘要清理与重新生成流程")
    print("=" * 70)
    print("\n⚠️  警告：此操作将删除所有现有的摘要和向量数据！")
    print("    - PostgreSQL: summaries表、topic_summary类型的embeddings")
    print("    - ChromaDB: topic_summary类型的向量")
    print()
    
    # 确认操作
    try:
        confirm = input("确认继续？(yes/no): ").strip().lower()
        if confirm not in ['yes', 'y']:
            print("\n❌ 操作已取消")
            return
    except:
        # 非交互式环境，直接执行
        pass
    
    print()
    
    # 第1步：清理旧数据
    await cleanup_old_data()
    
    # 第2步：重新生成
    await regenerate_all_summaries()
    
    print("\n🎉 完整流程执行完毕！")


if __name__ == "__main__":
    asyncio.run(main())

