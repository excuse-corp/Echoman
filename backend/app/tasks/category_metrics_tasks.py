"""
分类统计任务

定时重算分类统计指标
"""
import asyncio
import logging
from celery import shared_task

from app.core.database import get_async_session, reset_db_engine
from app.services.category_metrics_service import CategoryMetricsService

logger = logging.getLogger(__name__)


@shared_task(name="app.tasks.category_metrics_tasks.daily_recompute_metrics")
def daily_recompute_metrics():
    """
    每日重算分类统计指标
    
    执行时间：每天凌晨1:00
    计算内容：近一年（365天）的分类统计指标
    """
    logger.info("🔄 开始执行每日分类统计重算任务...")
    
    # 重置数据库引擎，确保在当前event loop中创建连接
    reset_db_engine()
    
    # 创建新的事件循环
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        result = loop.run_until_complete(recompute_metrics_async())
        logger.info(f"✅ 每日分类统计重算完成: {result}")
        return result
    except Exception as e:
        logger.error(f"❌ 每日分类统计重算失败: {e}", exc_info=True)
        return {"status": "failed", "error": str(e)}
    finally:
        loop.close()


async def recompute_metrics_async():
    """异步执行分类统计重算"""
    async_session = get_async_session()
    
    async with async_session() as db:
        service = CategoryMetricsService(db)
        
        # 重算并保存今天的指标
        result = await service.recompute_and_save_metrics(
            since_date=None,  # 今天
            rebuild=True  # 重建，删除旧数据
        )
        
        return result

