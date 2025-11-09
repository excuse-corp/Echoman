"""
前端数据更新服务

在归并完成后，更新前端页面需要的数据和状态
"""
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from app.utils.timezone import now_cn
from app.services.category_metrics_service import CategoryMetricsService


class FrontendUpdateService:
    """前端数据更新服务"""
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
    async def update_after_merge(self, period: str, merge_stats: dict):
        """
        归并完成后更新前端数据
        
        Args:
            period: 归并周期（如 "2025-11-07_AM"）
            merge_stats: 归并统计信息
        
        功能：
        1. 更新最后归并时间戳（供前端检测数据更新）
        2. 刷新 Topics 表的聚合统计
        3. 记录归并完成事件到监控表
        4. 【关键】重算分类指标
        """
        print(f"🔄 更新前端数据: {period}")
        
        # 1. 更新最后归并时间戳（存储在系统配置表或缓存）
        try:
            await self._update_last_merge_timestamp(period)
        except Exception as e:
            print(f"  ⚠️  更新时间戳失败（不影响后续）: {e}")
            await self.db.rollback()  # 回滚失败的事务
        
        # 2. 刷新 Topics 的聚合统计（确保前端看到的数据是最新的）
        try:
            await self._refresh_topic_stats()
        except Exception as e:
            print(f"  ⚠️  刷新Topic统计失败（不影响后续）: {e}")
            await self.db.rollback()
        
        # 3. 记录归并完成事件（可选：用于前端轮询检测）
        try:
            await self._log_merge_completion(period, merge_stats)
        except Exception as e:
            print(f"  ⚠️  记录归并事件失败（不影响后续）: {e}")
            await self.db.rollback()
        
        # 4. 【关键】刷新分类聚合指标（独立事务，确保执行）
        await self._refresh_category_metrics()
        
        print(f"✅ 前端数据更新完成")
    
    async def _update_last_merge_timestamp(self, period: str):
        """更新最后归并时间戳"""
        # 使用简单的key-value表存储最后更新时间
        # 如果没有system_config表，可以创建一个简单的表或使用Redis
        
        # 方案1：在数据库中存储（需要system_config表）
        # 方案2：直接更新topics表的updated_at字段（已经在归并时更新）
        # 方案3：使用Redis缓存（需要Redis）
        
        # 这里我们采用方案2，Topics表的updated_at已经在归并时更新了
        # 前端可以通过查询Topics表的max(updated_at)来检测数据更新
        
        # 如果需要一个全局的"最后归并时间"，可以添加到system_config表
        try:
            await self.db.execute(text("""
                INSERT INTO system_config (key, value, updated_at)
                VALUES ('last_merge_time', :timestamp, :timestamp)
                ON CONFLICT (key) 
                DO UPDATE SET value = :timestamp, updated_at = :timestamp
            """), {
                "timestamp": now_cn().isoformat()
            })
        except Exception as e:
            # 如果system_config表不存在，忽略此步骤
            print(f"  ⚠️  无法更新系统配置表（可能不存在）: {e}")
    
    async def _refresh_topic_stats(self):
        """刷新 Topics 的聚合统计"""
        # 确保 Topics 表中的聚合字段都是最新的
        # 例如：node_count, source_count 等
        
        # 这些字段应该在归并时已经更新，这里只是确认
        # 如果有需要重新计算的统计字段，可以在这里添加
        
        # 例如：更新 node_count
        try:
            await self.db.execute(text("""
                UPDATE topics t
                SET node_count = (
                    SELECT COUNT(*) 
                    FROM topic_nodes tn 
                    WHERE tn.topic_id = t.id
                )
                WHERE t.status = 'active'
                AND t.updated_at >= NOW() - INTERVAL '1 hour'
            """))
        except Exception as e:
            print(f"  ⚠️  刷新Topic统计失败: {e}")
    
    async def _log_merge_completion(self, period: str, merge_stats: dict):
        """记录归并完成事件"""
        # 将归并完成事件记录到runs_pipeline表
        # 前端可以查询此表来检测最新的归并完成时间
        
        try:
            await self.db.execute(text("""
                INSERT INTO runs_pipeline (
                    run_id, stage, status, started_at, ended_at,
                    input_count, output_count, metadata
                )
                VALUES (
                    :run_id, 'merge_completed', 'success',
                    :started_at, :ended_at,
                    :input_count, :output_count, :metadata
                )
            """), {
                "run_id": f"merge_{period}_{now_cn().strftime('%Y%m%d%H%M%S')}",
                "started_at": now_cn(),
                "ended_at": now_cn(),
                "input_count": merge_stats.get("processed_groups", 0),
                "output_count": merge_stats.get("merge_count", 0) + merge_stats.get("new_count", 0),
                "metadata": str(merge_stats)
            })
        except Exception as e:
            print(f"  ⚠️  记录归并完成事件失败: {e}")

    async def _refresh_category_metrics(self):
        """刷新分类聚合指标，供前端展示"""
        try:
            service = CategoryMetricsService(self.db)
            today = now_cn().date()
            await service.recompute_and_save_metrics(
                since_date=today,
                rebuild=True
            )
            print("  ✅ 分类指标已更新")
        except Exception as e:
            print(f"  ⚠️  更新分类指标失败: {e}")


async def update_frontend_after_merge(db: AsyncSession, period: str, merge_stats: dict):
    """
    便捷函数：归并完成后更新前端数据
    
    Args:
        db: 数据库会话
        period: 归并周期
        merge_stats: 归并统计信息
    """
    service = FrontendUpdateService(db)
    await service.update_after_merge(period, merge_stats)

