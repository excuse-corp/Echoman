"""
归并相关 Celery 任务

⚠️ 命名说明：
- halfday_merge 和 global_merge 是历史命名
- 实际功能分别对应【归并阶段一】和【归并阶段二】

【归并执行流程】
每日执行 4 轮归并（早间、上午、下午、傍晚）

  采集时间: 08:00, 10:00, 12:00, 14:00, 16:00, 18:00, 20:00, 22:00
       ↓
  08:05/08:20 → MORN 半日 + 全局归并（仅 08:00 数据）
  12:05/12:20 → AM   半日 + 全局归并（10:00/12:00 数据）
  18:05/18:20 → PM   半日 + 全局归并（14:00/16:00/18:00 数据）
  22:05/22:20 → EVE  半日 + 全局归并（20:00/22:00 数据）
          ├─ 热度归一化
          ├─ 向量聚类
          ├─ LLM判定
          ├─ 出现次数筛选（≥2次保留）
          └─ 输出: pending_global_merge
                   ↓
  12:30/18:30/22:30 → global_merge 任务（阶段二：整体归并）
          ├─ 向量检索历史Topics
          ├─ LLM关联判定
          ├─ 决策: merge（归入已有主题）or new（创建新主题）
          ├─ 更新Topics/TopicNodes/TopicHalfdayHeat表
          └─ 前端通过API轮询获取最新数据

【归并周期划分】
- 上午（AM）：8:00-12:00 的采集（3次）→ 12:15归并
- 下午（PM）：14:00-18:00 的采集（3次）→ 18:15归并
- 傍晚（EVE）：20:00-22:00 的采集（2次）→ 22:15归并
"""
from celery import shared_task
import asyncio
from app.utils.timezone import now_cn

from app.core.database import get_async_session, reset_db_engine
from app.services.heat_normalization import HeatNormalizationService
from app.services.halfday_merge import EventMergeService
from app.services.global_merge import GlobalMergeService


@shared_task(name="app.tasks.merge_tasks.halfday_merge")
def halfday_merge():
    """
    【归并阶段一】新事件归并任务
    
    职责：
    - 对当前时段内新采集的数据去噪、验证真实性
    - 过滤单次出现的噪音数据（出现次数 < 2）
    
    触发时间：每天4次（08:05 MORN，12:05 AM，18:05 PM，22:05 EVE）
    """
    print(f"🔄 【归并阶段一】开始执行新事件归并任务")
    
    # 重置数据库引擎，确保在当前event loop中创建连接
    reset_db_engine()
    
    # 创建新的事件循环以避免与Celery的事件循环冲突
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        result = loop.run_until_complete(run_halfday_merge_async())
    finally:
        loop.close()
    
    print(f"✅ 【归并阶段一】完成: {result}")
    return result


@shared_task(name="app.tasks.merge_tasks.global_merge")
def global_merge():
    """
    【归并阶段二】整体归并任务
    
    职责：
    - 将阶段一输出的验证事件与历史主题库比对
    - 通过向量检索 + LLM判定，决策是归入已有主题还是创建新主题
    - 更新 Topics、TopicNodes、TopicHalfdayHeat 表
    - 前端通过 API 轮询获取最新数据
    
    触发时间：每天4次（08:20 MORN，12:20 AM，18:20 PM，22:20 EVE）
    
    性能优化：批量处理、并行处理、限流、候选数量限制
    """
    print(f"🌍 【归并阶段二】开始执行整体归并任务")
    
    # 重置数据库引擎，确保在当前event loop中创建连接
    reset_db_engine()
    
    # 创建新的事件循环以避免与Celery的事件循环冲突
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        result = loop.run_until_complete(run_global_merge_async())
    finally:
        loop.close()
    
    print(f"✅ 【归并阶段二】完成: {result}")
    return result


async def run_halfday_merge_async():
    """异步执行新事件归并"""
    async_session = get_async_session()
    
    async with async_session() as db:
        try:
            # 1. 确定归并周期
            heat_service = HeatNormalizationService(db)
            period = heat_service.calculate_period()
            
            print(f"📅 归并周期: {period}")
            
            # 2. 热度归一化
            print("🔥 执行热度归一化...")
            heat_result = await heat_service.normalize_period_heat(period)
            print(f"  热度归一化完成: {heat_result.get('total_items', 0)} 条数据")
            
            # 3. 新事件归并
            print("🔗 执行新事件归并...")
            merge_service = EventMergeService(db)
            merge_result = await merge_service.run_event_merge(period)
            
            return {
                "status": "success",
                "period": period,
                "heat_result": heat_result,
                "merge_result": merge_result
            }
                
        except Exception as e:
            print(f"❌ 新事件归并失败: {e}")
            import traceback
            traceback.print_exc()
            return {
                "status": "failed",
                "period": period if 'period' in locals() else 'unknown',
                "error": str(e)
            }


async def run_global_merge_async():
    """异步执行整体归并"""
    async_session = get_async_session()
    
    async with async_session() as db:
        try:
            # 1. 确定归并周期
            heat_service = HeatNormalizationService(db)
            period = heat_service.calculate_period()
            
            print(f"📅 归并周期: {period}")
            
            # 2. 整体归并
            merge_service = GlobalMergeService(db)
            result = await merge_service.run_global_merge(period)
            
            return {
                "status": "success",
                "period": period,
                "result": result
            }
                
        except Exception as e:
            print(f"❌ 整体归并失败: {e}")
            import traceback
            traceback.print_exc()
            return {
                "status": "failed",
                "period": period if 'period' in locals() else 'unknown',
                "error": str(e)
            }
