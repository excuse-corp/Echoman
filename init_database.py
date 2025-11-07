#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
初始化数据库表
"""
import sys
import asyncio
from pathlib import Path

# 添加backend到路径
backend_dir = Path(__file__).parent / "backend"
sys.path.insert(0, str(backend_dir))

from sqlalchemy import text
from app.core.database import engine
from app.models import Base


async def init_tables():
    """创建所有数据库表"""
    print("🗄️  开始初始化数据库表...")
    
    async with engine.begin() as conn:
        # 先尝试创建pgvector扩展
        try:
            await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
            print("✅ pgvector扩展已创建")
        except Exception as e:
            print(f"⚠️  pgvector扩展不可用（将跳过embeddings表）: {e}")
        
        # 创建所有表（如果pgvector不可用，embeddings表会创建失败但其他表会成功）
        try:
            await conn.run_sync(Base.metadata.create_all)
            print("✅ 数据库表创建完成")
        except Exception as e:
            print(f"⚠️  部分表创建可能失败: {e}")
            # 尝试手动创建基础表（不包括embeddings）
            await conn.execute(text("""
                CREATE TABLE IF NOT EXISTS source_items (
                    id BIGSERIAL PRIMARY KEY,
                    platform VARCHAR(20) NOT NULL,
                    title VARCHAR(500) NOT NULL,
                    summary TEXT,
                    url VARCHAR(1000) NOT NULL,
                    published_at TIMESTAMP,
                    fetched_at TIMESTAMP NOT NULL,
                    interactions JSONB,
                    heat_value FLOAT,
                    heat_normalized FLOAT,
                    url_hash VARCHAR(64) NOT NULL,
                    content_hash VARCHAR(64) NOT NULL,
                    dedup_key VARCHAR(100) NOT NULL UNIQUE,
                    halfday_merge_group_id VARCHAR(50),
                    halfday_period VARCHAR(20),
                    occurrence_count INTEGER NOT NULL DEFAULT 1,
                    merge_status VARCHAR(20) NOT NULL,
                    embedding_id BIGINT,
                    run_id VARCHAR(50),
                    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
                );
                
                CREATE TABLE IF NOT EXISTS runs_ingest (
                    id BIGSERIAL PRIMARY KEY,
                    run_id VARCHAR(50) NOT NULL UNIQUE,
                    status VARCHAR(20) NOT NULL,
                    started_at TIMESTAMP,
                    ended_at TIMESTAMP,
                    duration_ms INTEGER,
                    total_platforms INTEGER,
                    success_platforms INTEGER,
                    failed_platforms INTEGER,
                    total_items INTEGER,
                    success_items INTEGER,
                    failed_items INTEGER,
                    error_summary VARCHAR(1000),
                    config JSONB,
                    platform_results JSONB,
                    parse_success_rate FLOAT,
                    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
                );
                
                CREATE TABLE IF NOT EXISTS topics (
                    id BIGSERIAL PRIMARY KEY,
                    title_key VARCHAR(500) NOT NULL,
                    first_seen TIMESTAMP NOT NULL,
                    last_active TIMESTAMP NOT NULL,
                    status VARCHAR(20) NOT NULL,
                    intensity_total INTEGER NOT NULL DEFAULT 0,
                    interaction_total BIGINT,
                    current_heat_normalized FLOAT,
                    heat_percentage FLOAT,
                    heat_score FLOAT,
                    occurrence_count INTEGER NOT NULL DEFAULT 0,
                    summary_id BIGINT,
                    category VARCHAR(50),
                    category_confidence FLOAT,
                    category_method VARCHAR(20),
                    category_updated_at TIMESTAMP,
                    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
                );
                
                CREATE TABLE IF NOT EXISTS topic_nodes (
                    id BIGSERIAL PRIMARY KEY,
                    topic_id BIGINT NOT NULL,
                    source_item_id BIGINT NOT NULL,
                    joined_at TIMESTAMP NOT NULL,
                    is_representative BOOLEAN NOT NULL DEFAULT FALSE,
                    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
                );
            """))
            print("✅ 基础表创建成功")
    
    await engine.dispose()
    print("✅ 数据库初始化完成")


if __name__ == "__main__":
    asyncio.run(init_tables())

