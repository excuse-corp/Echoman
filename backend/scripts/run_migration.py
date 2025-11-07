"""
执行数据库迁移脚本
"""
import sys
import os

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import asyncio
from sqlalchemy import text
from app.core.database import get_async_session


async def run_migration():
    """执行迁移SQL"""
    
    # 读取SQL文件
    sql_file = os.path.join(os.path.dirname(__file__), 'migrate_to_period_naming.sql')
    
    with open(sql_file, 'r', encoding='utf-8') as f:
        sql_content = f.read()
    
    # 分离SQL语句（排除注释和回滚部分）
    statements = []
    in_rollback = False
    
    for line in sql_content.split('\n'):
        # 跳过注释和空行
        line = line.strip()
        if not line or line.startswith('--'):
            if '回滚' in line or 'ROLLBACK' in line.upper():
                in_rollback = True
            continue
        
        # 跳过回滚部分
        if '/*' in line:
            in_rollback = True
        if '*/' in line:
            in_rollback = False
            continue
        
        if in_rollback:
            continue
        
        if line and not line.startswith('--'):
            statements.append(line)
    
    # 合并SQL语句
    sql = '\n'.join(statements)
    
    # 按分号分割独立语句
    individual_statements = [s.strip() + ';' for s in sql.split(';') if s.strip()]
    
    # 执行迁移
    async_session = get_async_session()
    
    async with async_session() as session:
        try:
            print("=" * 60)
            print("开始执行数据库迁移...")
            print("=" * 60)
            
            for idx, stmt in enumerate(individual_statements, 1):
                if not stmt.strip() or stmt.strip() == ';':
                    continue
                
                print(f"\n[{idx}/{len(individual_statements)}] 执行语句:")
                print(f"  {stmt[:100]}..." if len(stmt) > 100 else f"  {stmt}")
                
                try:
                    await session.execute(text(stmt))
                    print("  ✅ 成功")
                except Exception as e:
                    # 有些语句可能失败（比如表已存在），继续执行
                    print(f"  ⚠️  {str(e)[:100]}")
            
            # 提交事务
            await session.commit()
            
            print("\n" + "=" * 60)
            print("✅ 数据库迁移完成！")
            print("=" * 60)
            
            # 验证迁移结果
            print("\n验证迁移结果...")
            
            # 检查新表是否存在
            result = await session.execute(text("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables 
                    WHERE table_name = 'topic_period_heat'
                );
            """))
            exists = result.scalar()
            print(f"  topic_period_heat 表: {'✅ 存在' if exists else '❌ 不存在'}")
            
            # 检查新字段是否存在
            result = await session.execute(text("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = 'source_items' 
                AND column_name IN ('period', 'period_merge_group_id');
            """))
            columns = [row[0] for row in result.fetchall()]
            print(f"  source_items.period: {'✅ 存在' if 'period' in columns else '❌ 不存在'}")
            print(f"  source_items.period_merge_group_id: {'✅ 存在' if 'period_merge_group_id' in columns else '❌ 不存在'}")
            
            # 检查数据统计
            try:
                result = await session.execute(text("""
                    SELECT period, COUNT(*) as count
                    FROM source_items 
                    WHERE period IS NOT NULL
                    GROUP BY period
                    ORDER BY period;
                """))
                print("\n数据统计:")
                for row in result.fetchall():
                    print(f"  {row[0]}: {row[1]} 条")
            except:
                print("  （暂无数据）")
            
            return True
            
        except Exception as e:
            await session.rollback()
            print(f"\n❌ 迁移失败: {e}")
            import traceback
            traceback.print_exc()
            return False


if __name__ == "__main__":
    success = asyncio.run(run_migration())
    sys.exit(0 if success else 1)

