#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
数据库表初始化脚本
"""
import asyncio
import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
backend_dir = Path(__file__).parent.parent
sys.path.insert(0, str(backend_dir))

from sqlalchemy import text
from app.core.database import engine
from app.models import Base


async def create_tables():
    """创建所有数据库表"""
    print("🗄️  正在创建数据库表...")
    
    async with engine.begin() as conn:
        # 创建 pgvector 扩展
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))
        
        # 创建所有表
        await conn.run_sync(Base.metadata.create_all)

        # 初始化物化视图（topic_item_mv）
        await conn.execute(text("""
            CREATE MATERIALIZED VIEW IF NOT EXISTS topic_item_mv AS
            SELECT
              t.id AS topic_id,
              t.title_key AS title,
              s.content AS summary,
              t.first_seen,
              t.last_active,
              t.status,
              t.category,
              t.intensity_total,
              t.current_heat_normalized AS heat_normalized,
              EXTRACT(EPOCH FROM (t.last_active - t.first_seen)) / 3600.0 AS echo_length_hours,
              si.id AS item_id,
              si.title AS item_title,
              si.summary AS item_summary,
              si.url AS item_url,
              si.platform AS item_platform,
              si.published_at AS item_published_at,
              si.fetched_at AS item_fetched_at
            FROM topics t
            LEFT JOIN summaries s ON s.id = t.summary_id
            LEFT JOIN topic_nodes tn ON tn.topic_id = t.id
            LEFT JOIN source_items si ON si.id = tn.source_item_id;
        """))

        await conn.execute(text("""
            CREATE UNIQUE INDEX IF NOT EXISTS idx_topic_item_mv_unique
              ON topic_item_mv (topic_id, item_id);
        """))
        await conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_topic_item_mv_last_active
              ON topic_item_mv (last_active);
        """))
        await conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_topic_item_mv_category
              ON topic_item_mv (category);
        """))
        await conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_topic_item_mv_platform
              ON topic_item_mv (item_platform);
        """))

        await conn.execute(text("REFRESH MATERIALIZED VIEW topic_item_mv"))
    
    print("✅ 数据库表创建完成")
    
    # 显示所有创建的表
    async with engine.connect() as conn:
        result = await conn.execute(
            text("SELECT tablename FROM pg_tables WHERE schemaname = 'public' ORDER BY tablename")
        )
        tables = result.fetchall()
        
        print("\n📋 已创建的表:")
        for table in tables:
            print(f"  - {table[0]}")


async def drop_tables():
    """删除所有数据库表（危险操作）"""
    print("⚠️  警告: 即将删除所有数据库表")
    response = input("确定要继续吗? (yes/no): ").strip().lower()
    
    if response != "yes":
        print("❌ 操作已取消")
        return
    
    print("🗑️  正在删除数据库表...")
    
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    
    print("✅ 数据库表已删除")


async def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(description="数据库表管理工具")
    parser.add_argument(
        "action",
        choices=["create", "drop", "recreate"],
        help="操作类型: create(创建), drop(删除), recreate(重新创建)"
    )
    
    args = parser.parse_args()
    
    try:
        if args.action == "create":
            await create_tables()
        elif args.action == "drop":
            await drop_tables()
        elif args.action == "recreate":
            await drop_tables()
            await create_tables()
    except Exception as e:
        print(f"❌ 操作失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
