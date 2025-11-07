#!/usr/bin/env python3
"""
向量索引初始化脚本

在数据库中创建pgvector索引以优化向量检索性能
"""
import asyncio
import sys
from pathlib import Path

# 添加项目根目录到Python路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.db import get_async_session_context
from app.services.vector_optimization import VectorOptimizationService


async def main():
    """主函数"""
    print("=" * 60)
    print("向量索引初始化工具")
    print("=" * 60)
    print()
    
    async with get_async_session_context() as db:
        service = VectorOptimizationService()
        
        # 1. 分析当前索引状态
        print("📊 分析当前索引状态...")
        stats = await service.analyze_index_usage(db)
        
        print(f"\n当前状态:")
        print(f"  表名: {stats['table_name']}")
        print(f"  总行数: {stats['total_rows']}")
        print(f"  表大小: {stats['table_size']}")
        print(f"  现有向量索引: {len(stats['indexes'])} 个")
        
        if stats['indexes']:
            for idx in stats['indexes']:
                print(f"    - {idx['name']}")
        
        print()
        
        # 2. 询问是否创建索引
        if stats['total_rows'] == 0:
            print("⚠️  表中暂无数据，建议在数据导入后再创建索引")
            return
        
        # 根据数据量选择索引类型
        if stats['total_rows'] < 100000:
            print(f"💡 数据量较小（{stats['total_rows']} 行）")
            print("   推荐: 使用HNSW索引（更快查询，适合小规模）")
            index_type = "hnsw"
        else:
            print(f"💡 数据量较大（{stats['total_rows']} 行）")
            print("   推荐: 使用IVFFlat索引（适合大规模）")
            index_type = "ivfflat"
        
        print()
        response = input(f"是否创建{index_type.upper()}索引? (y/n) [y]: ").strip().lower()
        
        if response in ['', 'y', 'yes']:
            # 3. 创建索引
            if index_type == "ivfflat":
                result = await service.create_ivfflat_index(db)
            else:
                result = await service.create_hnsw_index(db)
            
            if result['status'] == 'success':
                print()
                print("✅ 索引创建成功!")
                print(f"   索引名: {result['index_name']}")
                
                # 4. 优化查询性能
                print()
                print("🔧 优化查询性能...")
                await service.optimize_query_performance(db, probes=10)
                
                # 5. 执行VACUUM ANALYZE
                print()
                print("🔧 优化表统计信息...")
                await service.vacuum_analyze(db)
                
                # 6. 再次查看索引状态
                print()
                print("📊 索引创建后状态:")
                new_stats = await service.analyze_index_usage(db)
                print(f"  向量索引: {len(new_stats['indexes'])} 个")
                for idx in new_stats['indexes']:
                    print(f"    - {idx['name']}")
                
                print()
                print("=" * 60)
                print("✅ 向量索引初始化完成！")
                print("=" * 60)
                
            else:
                print()
                print(f"❌ 索引创建失败: {result.get('error')}")
        else:
            print("⏭️  跳过索引创建")
    
    print()


if __name__ == "__main__":
    asyncio.run(main())

