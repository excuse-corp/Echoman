#!/usr/bin/env python
"""
为现有的Summaries批量生成向量
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import select, and_
from app.core.database import get_async_session
from app.models import Summary, Embedding
from app.services.llm import get_embedding_provider
from app.services.vector_service import get_vector_service


async def init_summary_embeddings():
    """为所有没有向量的Summaries生成向量"""
    
    async_session = get_async_session()
    
    async with async_session() as db:
        print("=" * 70)
        print("为现有Summaries批量生成向量")
        print("=" * 70)
        
        # 1. 查找没有向量的Summaries
        stmt = select(Summary).where(
            ~Summary.id.in_(
                select(Embedding.object_id).where(
                    Embedding.object_type == 'topic_summary'
                )
            )
        ).order_by(Summary.generated_at.desc())
        
        summaries = (await db.execute(stmt)).scalars().all()
        
        if not summaries:
            print("✅ 所有Summaries都已有向量")
            return
        
        print(f"📊 找到 {len(summaries)} 个需要生成向量的Summaries")
        print()
        
        # 2. 批量生成向量
        embedding_provider = get_embedding_provider()
        vector_service = get_vector_service()
        
        success_count = 0
        failed_count = 0
        
        for i, summary in enumerate(summaries, 1):
            try:
                print(f"[{i}/{len(summaries)}] 处理 Summary {summary.id} (Topic {summary.topic_id})...")
                
                # 生成向量
                vectors = await embedding_provider.embedding([summary.content])
                
                # 保存到PostgreSQL
                embedding = Embedding(
                    object_type="topic_summary",
                    object_id=summary.id,
                    provider=embedding_provider.get_provider_name(),
                    model=embedding_provider.model,
                    vector=vectors[0]
                )
                db.add(embedding)
                await db.commit()
                
                # 同步到Chroma
                if vector_service.db_type == "chroma":
                    vector_service.add_embeddings(
                        ids=[f"topic_summary_{summary.id}"],
                        embeddings=[vectors[0]],
                        metadatas=[{
                            "object_type": "topic_summary",
                            "object_id": int(summary.id),
                            "topic_id": int(summary.topic_id),
                            "generated_at": summary.generated_at.timestamp()
                        }],
                        documents=[summary.content[:500]]
                    )
                
                success_count += 1
                print(f"  ✅ 成功")
                
            except Exception as e:
                failed_count += 1
                print(f"  ❌ 失败: {e}")
                await db.rollback()
            
            # 每10个打印一次进度
            if i % 10 == 0:
                print(f"\n进度: {i}/{len(summaries)} ({i/len(summaries)*100:.1f}%)\n")
        
        print()
        print("=" * 70)
        print(f"✅ 批量生成完成")
        print(f"   成功: {success_count}个")
        print(f"   失败: {failed_count}个")
        print("=" * 70)


if __name__ == "__main__":
    asyncio.run(init_summary_embeddings())

