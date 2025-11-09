"""
为PM周期数据补充向量
"""
import asyncio
import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import select, and_
from app.core.database import get_async_session
from app.models import SourceItem, Embedding
from app.services.llm import get_embedding_provider
from app.services.vector_service import get_vector_service
from app.config import settings


async def fix_pm_vectors():
    """为PM周期数据补充向量"""
    
    async_session = get_async_session()
    
    async with async_session() as db:
        try:
            # 1. 获取没有embedding_id的PM数据
            stmt = select(SourceItem).where(
                and_(
                    SourceItem.period == "2025-11-07_PM",
                    SourceItem.merge_status == "pending_event_merge",
                    SourceItem.embedding_id.is_(None)
                )
            )
            result = await db.execute(stmt)
            items = result.scalars().all()
            
            if not items:
                print("✅ 所有PM数据都已有向量")
                return
            
            print(f"📊 找到 {len(items)} 条需要生成向量的数据")
            
            # 2. 准备文本
            texts = [
                f"{item.title} {item.summary or ''}" 
                for item in items
            ]
            
            # 3. 批量向量化
            print("🔄 开始生成向量...")
            embedding_provider = get_embedding_provider()
            vectors = await embedding_provider.embedding(texts)
            print(f"✅ 向量生成完成: {len(vectors)} 个")
            
            # 4. 保存向量到PostgreSQL
            print("💾 保存向量到PostgreSQL...")
            embeddings_to_create = []
            for item, vector in zip(items, vectors):
                embedding = Embedding(
                    object_type="source_item",
                    object_id=item.id,
                    provider=embedding_provider.get_provider_name(),
                    model=embedding_provider.model,
                    vector=vector
                )
                db.add(embedding)
                embeddings_to_create.append((item, embedding))
            
            # 先flush以获取embedding的ID
            await db.flush()
            
            # 更新 source_item 的 embedding_id
            for item, embedding in embeddings_to_create:
                item.embedding_id = embedding.id
            
            await db.commit()
            print(f"✅ PostgreSQL保存完成: {len(embeddings_to_create)} 条")
            
            # 5. 同步到Chroma向量数据库
            try:
                print("🔄 同步到Chroma向量数据库...")
                vector_service = get_vector_service()
                if vector_service.db_type == "chroma":
                    ids = [f"source_item_{item.id}" for item in items]
                    metadatas = [
                        {
                            "object_type": "source_item",
                            "object_id": int(item.id),
                            "platform": item.platform,
                            "title": item.title[:200]
                        }
                        for item in items
                    ]
                    documents = [f"{item.title} {item.summary or ''}"[:500] for item in items]
                    
                    vector_service.add_embeddings(
                        ids=ids,
                        embeddings=vectors,
                        metadatas=metadatas,
                        documents=documents
                    )
                    print(f"✅ Chroma同步完成: {len(vectors)} 个向量")
                else:
                    print(f"⚠️  向量数据库类型为 {vector_service.db_type}，跳过Chroma同步")
            except Exception as chroma_error:
                print(f"⚠️  Chroma同步失败（不影响主流程）: {chroma_error}")
            
            # 6. 验证结果
            print("\n📊 验证结果...")
            stmt = select(SourceItem).where(
                and_(
                    SourceItem.period == "2025-11-07_PM",
                    SourceItem.merge_status == "pending_event_merge"
                )
            )
            result = await db.execute(stmt)
            all_items = result.scalars().all()
            
            has_embedding = sum(1 for item in all_items if item.embedding_id is not None)
            print(f"✅ PM周期数据: {len(all_items)} 条")
            print(f"✅ 有向量: {has_embedding} 条 ({has_embedding/len(all_items)*100:.1f}%)")
            
        except Exception as e:
            print(f"❌ 错误: {e}")
            import traceback
            traceback.print_exc()
            await db.rollback()


if __name__ == "__main__":
    print("=" * 60)
    print("为PM周期数据补充向量")
    print("=" * 60)
    asyncio.run(fix_pm_vectors())
    print("=" * 60)
    print("完成")
    print("=" * 60)

