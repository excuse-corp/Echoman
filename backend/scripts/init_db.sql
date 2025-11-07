-- 初始化数据库脚本

-- 创建 pgvector 扩展
CREATE EXTENSION IF NOT EXISTS vector;

-- 创建 pg_trgm 扩展（用于文本搜索）
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- 设置时区
SET timezone = 'UTC';

