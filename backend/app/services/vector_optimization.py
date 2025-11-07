"""
向量检索优化服务

提供pgvector索引管理和优化功能
"""
from typing import Optional, List, Dict
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from app.config import settings


class VectorOptimizationService:
    """向量检索优化服务"""
    
    def __init__(self):
        self.settings = settings
        
    async def create_ivfflat_index(
        self,
        db: AsyncSession,
        table_name: str = "embeddings",
        column_name: str = "vector",
        lists: Optional[int] = None,
        index_name: Optional[str] = None
    ) -> Dict:
        """
        创建IVFFlat索引
        
        IVFFlat索引使用倒排文件（inverted file）加速向量检索
        适用于大规模数据集（>10万条向量）
        
        Args:
            db: 数据库会话
            table_name: 表名
            column_name: 向量列名
            lists: 聚类中心数量（默认为行数的平方根）
            index_name: 索引名称
            
        Returns:
            索引创建结果
        """
        # 确定lists参数
        if lists is None:
            # 推荐值：对于 N 行数据，使用 sqrt(N) 或 N/1000
            count_stmt = text(f"SELECT COUNT(*) FROM {table_name}")
            result = await db.execute(count_stmt)
            row_count = result.scalar()
            
            if row_count > 1000000:
                lists = int(row_count / 1000)
            elif row_count > 100000:
                lists = int(row_count ** 0.5)
            else:
                lists = 100  # 小数据集使用默认值
        
        # 确定索引名称
        if index_name is None:
            index_name = f"{table_name}_{column_name}_ivfflat_idx"
        
        # 创建索引SQL
        create_index_sql = text(f"""
            CREATE INDEX IF NOT EXISTS {index_name}
            ON {table_name}
            USING ivfflat ({column_name} vector_cosine_ops)
            WITH (lists = {lists})
        """)
        
        try:
            print(f"🔧 开始创建IVFFlat索引...")
            print(f"   表名: {table_name}")
            print(f"   列名: {column_name}")
            print(f"   lists: {lists}")
            
            await db.execute(create_index_sql)
            await db.commit()
            
            print(f"✅ 索引创建成功: {index_name}")
            
            return {
                "status": "success",
                "index_name": index_name,
                "lists": lists,
                "table_name": table_name
            }
            
        except Exception as e:
            print(f"❌ 索引创建失败: {e}")
            await db.rollback()
            return {
                "status": "error",
                "error": str(e)
            }
    
    async def create_hnsw_index(
        self,
        db: AsyncSession,
        table_name: str = "embeddings",
        column_name: str = "vector",
        m: int = 16,
        ef_construction: int = 64,
        index_name: Optional[str] = None
    ) -> Dict:
        """
        创建HNSW索引
        
        HNSW（Hierarchical Navigable Small World）索引
        提供更高的查询性能，但构建时间较长
        
        Args:
            db: 数据库会话
            table_name: 表名
            column_name: 向量列名
            m: 每层的最大连接数（默认16）
            ef_construction: 构建时的搜索候选数（默认64）
            index_name: 索引名称
            
        Returns:
            索引创建结果
        """
        if index_name is None:
            index_name = f"{table_name}_{column_name}_hnsw_idx"
        
        create_index_sql = text(f"""
            CREATE INDEX IF NOT EXISTS {index_name}
            ON {table_name}
            USING hnsw ({column_name} vector_cosine_ops)
            WITH (m = {m}, ef_construction = {ef_construction})
        """)
        
        try:
            print(f"🔧 开始创建HNSW索引...")
            print(f"   表名: {table_name}")
            print(f"   m: {m}")
            print(f"   ef_construction: {ef_construction}")
            
            await db.execute(create_index_sql)
            await db.commit()
            
            print(f"✅ 索引创建成功: {index_name}")
            
            return {
                "status": "success",
                "index_name": index_name,
                "m": m,
                "ef_construction": ef_construction
            }
            
        except Exception as e:
            print(f"❌ 索引创建失败: {e}")
            await db.rollback()
            return {
                "status": "error",
                "error": str(e)
            }
    
    async def optimize_query_performance(
        self,
        db: AsyncSession,
        probes: int = 10
    ):
        """
        优化查询性能
        
        设置查询时的探测数量（probes）
        更多probes = 更高准确率，更慢速度
        
        Args:
            db: 数据库会话
            probes: 探测数量（默认10，范围1-lists）
        """
        set_probes_sql = text(f"SET ivfflat.probes = {probes}")
        await db.execute(set_probes_sql)
        
        print(f"✅ 设置查询探测数: {probes}")
    
    async def analyze_index_usage(
        self,
        db: AsyncSession,
        table_name: str = "embeddings"
    ) -> Dict:
        """
        分析索引使用情况
        
        Args:
            db: 数据库会话
            table_name: 表名
            
        Returns:
            索引统计信息
        """
        # 查询表的索引信息
        index_info_sql = text(f"""
            SELECT 
                indexname,
                indexdef
            FROM pg_indexes
            WHERE tablename = '{table_name}'
            AND indexname LIKE '%vector%'
        """)
        
        result = await db.execute(index_info_sql)
        indexes = result.fetchall()
        
        # 查询表统计
        stats_sql = text(f"""
            SELECT 
                COUNT(*) as total_rows,
                pg_size_pretty(pg_total_relation_size('{table_name}')) as table_size
            FROM {table_name}
        """)
        
        stats_result = await db.execute(stats_sql)
        stats = stats_result.fetchone()
        
        return {
            "table_name": table_name,
            "total_rows": stats[0] if stats else 0,
            "table_size": stats[1] if stats else "未知",
            "indexes": [
                {"name": idx[0], "definition": idx[1]}
                for idx in indexes
            ]
        }
    
    async def vacuum_analyze(
        self,
        db: AsyncSession,
        table_name: str = "embeddings"
    ):
        """
        执行VACUUM ANALYZE优化表
        
        定期执行以保持索引性能
        
        Args:
            db: 数据库会话
            table_name: 表名
        """
        try:
            # 注意：VACUUM不能在事务中执行
            # 需要使用autocommit模式
            await db.connection(execution_options={"isolation_level": "AUTOCOMMIT"})
            
            vacuum_sql = text(f"VACUUM ANALYZE {table_name}")
            await db.execute(vacuum_sql)
            
            print(f"✅ VACUUM ANALYZE完成: {table_name}")
            
        except Exception as e:
            print(f"⚠️  VACUUM ANALYZE失败: {e}")
    
    async def drop_index(
        self,
        db: AsyncSession,
        index_name: str
    ):
        """
        删除索引
        
        Args:
            db: 数据库会话
            index_name: 索引名称
        """
        drop_sql = text(f"DROP INDEX IF EXISTS {index_name}")
        
        try:
            await db.execute(drop_sql)
            await db.commit()
            print(f"✅ 索引已删除: {index_name}")
            
        except Exception as e:
            print(f"❌ 删除索引失败: {e}")
            await db.rollback()
    
    async def benchmark_query(
        self,
        db: AsyncSession,
        query_vector: List[float],
        k: int = 10,
        table_name: str = "embeddings"
    ) -> Dict:
        """
        测试查询性能
        
        Args:
            db: 数据库会话
            query_vector: 查询向量
            k: 返回Top-K结果
            table_name: 表名
            
        Returns:
            性能统计
        """
        import time
        
        # 构造查询向量字符串
        vector_str = f"[{','.join(map(str, query_vector))}]"
        
        # 启用查询计划分析
        explain_sql = text(f"""
            EXPLAIN ANALYZE
            SELECT id, vector <=> '{vector_str}'::vector AS distance
            FROM {table_name}
            ORDER BY distance
            LIMIT {k}
        """)
        
        start_time = time.time()
        result = await db.execute(explain_sql)
        query_plan = result.fetchall()
        elapsed_time = (time.time() - start_time) * 1000  # 转换为毫秒
        
        return {
            "query_time_ms": round(elapsed_time, 2),
            "top_k": k,
            "query_plan": [row[0] for row in query_plan]
        }


# 提供便捷的索引初始化函数
async def initialize_vector_indexes(db: AsyncSession):
    """
    初始化所有向量索引
    
    建议在数据导入后执行
    """
    service = VectorOptimizationService()
    
    print("🚀 开始初始化向量索引...")
    
    # 为embeddings表创建IVFFlat索引
    result = await service.create_ivfflat_index(
        db,
        table_name="embeddings",
        column_name="vector"
    )
    
    if result["status"] == "success":
        print("✅ 向量索引初始化完成")
    else:
        print(f"❌ 向量索引初始化失败: {result.get('error')}")
    
    # 分析索引使用情况
    stats = await service.analyze_index_usage(db)
    print(f"\n📊 索引统计:")
    print(f"   总行数: {stats['total_rows']}")
    print(f"   表大小: {stats['table_size']}")
    print(f"   索引数: {len(stats['indexes'])}")

