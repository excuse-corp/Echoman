"""
采集相关 Celery 任务
"""
from celery import shared_task
from sqlalchemy.ext.asyncio import AsyncSession
import asyncio

from app.config import settings
from app.core.database import get_async_session, reset_db_engine
from app.services.ingestion import IngestionService


@shared_task(name="app.tasks.ingestion_tasks.scheduled_ingestion")
def scheduled_ingestion():
    """
    定时采集任务
    
    每2小时执行一次（8:00-22:00）
    """
    print("🚀 开始执行定时采集任务...")
    
    # 重置数据库引擎，确保在当前event loop中创建连接
    reset_db_engine()
    
    # 在 Celery Worker 中，需要显式创建新的事件循环以避免冲突
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        result = loop.run_until_complete(run_ingestion_async())
    finally:
        loop.close()
    
    print(f"✅ 采集任务完成: {result}")
    return result


@shared_task(name="app.tasks.ingestion_tasks.manual_ingestion")
def manual_ingestion(platforms=None, limit=30):
    """
    手动触发采集任务
    
    Args:
        platforms: 平台列表
        limit: 每平台采集条数
    """
    print(f"🚀 开始执行手动采集任务: platforms={platforms}, limit={limit}")
    
    # 重置数据库引擎，确保在当前event loop中创建连接
    reset_db_engine()
    
    # 在 Celery Worker 中，需要显式创建新的事件循环以避免冲突
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        result = loop.run_until_complete(run_ingestion_async(platforms=platforms, limit=limit))
    finally:
        loop.close()
    
    print(f"✅ 采集任务完成: {result}")
    return result


async def run_ingestion_async(platforms=None, limit=30):
    """
    异步执行采集
    
    Args:
        platforms: 平台列表
        limit: 每平台采集条数
        
    Returns:
        采集结果字典
    """
    async_session = get_async_session()
    async with async_session() as db:
        service = IngestionService(db)
        
        try:
            result = await service.run_ingestion(
                platforms=platforms,
                limit=limit
            )
            return {
                "status": "success",
                "run_id": result["run_id"],
                "total_items": result["total_items"],
                "success_items": result["success_items"]
            }
        except Exception as e:
            print(f"❌ 采集失败: {e}")
            return {
                "status": "failed",
                "error": str(e)
            }


# 示例：测试任务
@shared_task(name="app.tasks.ingestion_tasks.test_task")
def test_task():
    """测试任务"""
    print("✅ Celery 测试任务执行成功")
    return {"status": "ok", "message": "Celery is working"}

