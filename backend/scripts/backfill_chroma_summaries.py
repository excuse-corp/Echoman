"""
将历史摘要向量写入 Chroma（纯 Chroma 模式补录脚本）

用法：
    PYTHONPATH=. conda run -n echoman python backend/scripts/backfill_chroma_summaries.py

说明：
    - 仅写入 Chroma，不依赖 pgvector。
    - 使用批处理，避免一次性请求过大。
    - 采用 upsert，重复运行也不会报错（会覆盖已有同 ID 的记录）。
"""
import asyncio
from typing import List

from sqlalchemy import select, func

from app.core.database import get_async_session
from app.models import Summary
from app.services.llm import get_embedding_provider
from app.services.vector_service import get_vector_service


BATCH_SIZE = 32  # 单批处理数量，可按需要调整


async def fetch_summaries(session, offset: int, limit: int) -> List[Summary]:
    stmt = (
        select(Summary)
        .order_by(Summary.id)
        .offset(offset)
        .limit(limit)
    )
    result = await session.execute(stmt)
    return result.scalars().all()


async def main():
    vector_service = get_vector_service()
    if vector_service.db_type != "chroma" or not vector_service.collection:
        raise RuntimeError("Chroma 未初始化，无法补写摘要向量")

    embedding_provider = get_embedding_provider()

    session_maker = get_async_session()
    async with session_maker() as session:
        total = (
            await session.execute(select(func.count()).select_from(Summary))
        ).scalar_one()
        print(f"🔢 待处理摘要总数: {total}")

        processed = 0
        offset = 0

        while offset < total:
            summaries = await fetch_summaries(session, offset, BATCH_SIZE)
            if not summaries:
                break

            texts = [s.content for s in summaries]
            vectors = await embedding_provider.embedding(texts)

            ids = [f"topic_summary_{s.id}" for s in summaries]
            metadatas = [
                {
                    "object_type": "topic_summary",
                    "object_id": int(s.id),
                    "topic_id": int(s.topic_id),
                    "generated_at": s.generated_at.timestamp() if s.generated_at else None,
                }
                for s in summaries
            ]
            documents = [text[:500] for text in texts]

            # 采用 upsert，避免重复报错
            vector_service.collection.upsert(
                ids=ids,
                embeddings=vectors,
                metadatas=metadatas,
                documents=documents,
            )

            processed += len(summaries)
            offset += len(summaries)
            print(f"✅ 已写入 {processed}/{total}")

    stats = vector_service.get_collection_stats()
    print(f"📊 完成，当前 Chroma 计数: {stats}")


if __name__ == "__main__":
    asyncio.run(main())
