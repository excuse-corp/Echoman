#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Cleanup noise topics/source_items like "点击查看更多实时热点".

Default is dry-run. Use --apply to delete.
"""
import argparse
import asyncio
import sys
from pathlib import Path
from typing import List, Set

# Add backend root to sys.path
backend_dir = Path(__file__).parent.parent
sys.path.insert(0, str(backend_dir))

from sqlalchemy import delete, or_, select

from app.core.database import get_async_session
from app.models import SourceItem, Topic, TopicNode, Summary
from app.services.vector_service import get_vector_service

DEFAULT_TITLES = ["点击查看更多实时热点"]
DEFAULT_URL_KEYWORDS = ["top_news_list.d.html", "top_news_list"]


def _build_or_conditions(titles: List[str], url_keywords: List[str]):
    conditions = []
    if titles:
        conditions.append(SourceItem.title.in_(titles))
    if url_keywords:
        for keyword in url_keywords:
            conditions.append(SourceItem.url.contains(keyword))
    return conditions


async def cleanup(apply: bool, titles: List[str], url_keywords: List[str]) -> None:
    session_maker = get_async_session()

    async with session_maker() as session:
        conditions = _build_or_conditions(titles, url_keywords)
        if not conditions:
            print("❌ 未提供清理条件，已退出")
            return

        # Collect source items
        stmt = select(SourceItem.id).where(or_(*conditions))
        result = await session.execute(stmt)
        source_item_ids = [row[0] for row in result.all()]

        # Collect topics by title
        topic_ids: Set[int] = set()
        if titles:
            topic_result = await session.execute(
                select(Topic.id).where(Topic.title_key.in_(titles))
            )
            topic_ids.update([row[0] for row in topic_result.all()])

        # Collect topics linked to source items
        if source_item_ids:
            node_result = await session.execute(
                select(TopicNode.topic_id).where(TopicNode.source_item_id.in_(source_item_ids))
            )
            topic_ids.update([row[0] for row in node_result.all()])

        # Collect summary ids for deletion in vector store
        summary_ids: List[int] = []
        if topic_ids:
            summary_result = await session.execute(
                select(Summary.id).where(Summary.topic_id.in_(list(topic_ids)))
            )
            summary_ids = [row[0] for row in summary_result.all()]

        print("\n🧹 噪音清理预览:")
        print(f"- SourceItems: {len(source_item_ids)}")
        print(f"- Topics: {len(topic_ids)}")
        print(f"- Summaries: {len(summary_ids)}")

        if not apply:
            print("\nℹ️  Dry-run 完成（未执行删除）。使用 --apply 执行实际删除。")
            return

        # Delete topics (cascade deletes nodes/period_heats/summaries in DB)
        if topic_ids:
            topic_result = await session.execute(
                select(Topic).where(Topic.id.in_(list(topic_ids)))
            )
            for topic in topic_result.scalars().all():
                await session.delete(topic)

        # Delete source items
        if source_item_ids:
            await session.execute(delete(SourceItem).where(SourceItem.id.in_(source_item_ids)))

        await session.commit()

    # Cleanup vectors in Chroma (best-effort)
    vector_service = get_vector_service()
    if vector_service.db_type == "chroma":
        if summary_ids:
            vector_service.delete_by_ids([f"topic_summary_{sid}" for sid in summary_ids])
        if source_item_ids:
            vector_service.delete_by_ids([f"source_item_{sid}" for sid in source_item_ids])

    print("\n✅ 噪音数据清理完成")


def main() -> None:
    parser = argparse.ArgumentParser(description="Cleanup noise topics/source_items")
    parser.add_argument(
        "--title",
        action="append",
        default=None,
        help="Noise title to delete (repeatable)."
    )
    parser.add_argument(
        "--url-keyword",
        action="append",
        default=None,
        help="URL keyword to delete (repeatable)."
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply deletions (default is dry-run)."
    )

    args = parser.parse_args()
    titles = args.title if args.title else DEFAULT_TITLES
    url_keywords = args.url_keyword if args.url_keyword else DEFAULT_URL_KEYWORDS

    asyncio.run(cleanup(args.apply, titles, url_keywords))


if __name__ == "__main__":
    main()
