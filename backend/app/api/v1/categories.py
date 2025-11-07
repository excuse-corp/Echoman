"""
分类相关API路由
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, desc
from typing import Optional, List
from datetime import datetime, timedelta

from app.core import get_db
from app.services.category_metrics_service import CategoryMetricsService
from app.models.metrics import CategoryDayMetrics
from app.schemas.metrics import TimeSeriesPoint, CategoryTimeSeriesResponse
from app.utils.timezone import now_cn

router = APIRouter()


@router.get("")
async def get_categories():
    """
    获取分类列表
    
    Returns:
        分类列表，包含key和display名称
    """
    return {
        "items": [
            {"key": "entertainment", "display": "娱乐八卦类事件"},
            {"key": "current_affairs", "display": "社会实事类事件"},
            {"key": "sports_esports", "display": "体育电竞类事件"}
        ]
    }


@router.get("/metrics/summary")
async def get_category_metrics_summary(
    window_days: int = Query(365, description="统计窗口天数，默认365天（一年）"),
    ended_only: bool = Query(False, description="是否只统计已结束的话题"),
    use_cache: bool = Query(True, description="是否使用预计算缓存"),
    db: AsyncSession = Depends(get_db)
):
    """
    获取分类统计摘要
    
    返回三个分类的回声时长统计（平均/最长/最短）及辅助指标
    
    Args:
        window_days: 统计窗口天数，默认365天
        ended_only: 是否只统计已结束的话题
        use_cache: 是否使用预计算缓存（推荐）
        
    Returns:
        分类统计摘要数据
    """
    try:
        service = CategoryMetricsService(db)
        
        # 如果使用缓存，优先返回预计算结果
        if use_cache:
            cached_result = await service.get_latest_precomputed_metrics()
            if cached_result:
                return cached_result
        
        # 实时计算
        result = await service.get_category_metrics_summary(
            window_days=window_days,
            ended_only=ended_only
        )
        
        return result
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取分类统计失败: {str(e)}")


@router.post("/metrics/recompute")
async def recompute_category_metrics(
    since_date: Optional[str] = Query(None, description="从哪个日期开始重算，格式YYYY-MM-DD"),
    rebuild: bool = Query(False, description="是否重建（删除旧数据）"),
    db: AsyncSession = Depends(get_db)
):
    """
    重新计算分类指标（管理接口）
    
    离线批量重算分类统计指标并保存到数据库
    
    Args:
        since_date: 从哪个日期开始重算，None表示今天
        rebuild: 是否重建（删除指定日期的旧数据）
        
    Returns:
        重算结果统计
    """
    try:
        service = CategoryMetricsService(db)
        
        # 解析日期
        target_date = None
        if since_date:
            try:
                target_date = datetime.strptime(since_date, "%Y-%m-%d")
            except ValueError:
                raise HTTPException(status_code=400, detail="日期格式错误，应为YYYY-MM-DD")
        
        result = await service.recompute_and_save_metrics(
            since_date=target_date,
            rebuild=rebuild
        )
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"重算分类指标失败: {str(e)}")


@router.get("/metrics/timeseries", response_model=CategoryTimeSeriesResponse)
async def get_category_metrics_timeseries(
    category: str = Query(..., description="分类（entertainment|current_affairs|sports_esports）"),
    metric: str = Query(..., description="指标名称（avg_length_hours|topics_count|intensity_avg等）"),
    days: int = Query(30, ge=1, le=365, description="查询天数，默认30天"),
    db: AsyncSession = Depends(get_db)
):
    """
    获取分类指标时序数据
    
    用于展示分类统计趋势图
    
    Args:
        category: 分类名称
        metric: 指标名称，可选值：
            - avg_length_hours: 平均回声时长
            - max_length_hours: 最长回声时长
            - min_length_hours: 最短回声时长
            - topics_count: 话题总数
            - topics_active: 活跃话题数
            - topics_ended: 已结束话题数
            - intensity_sum: 强度总和
            - intensity_avg: 平均强度
            - intensity_max: 最大强度
            - heat_sum: 热度总和
            - heat_avg: 平均热度
        days: 查询天数
        
    Returns:
        时序数据列表
    """
    try:
        # 验证分类
        valid_categories = ["entertainment", "current_affairs", "sports_esports"]
        if category not in valid_categories:
            raise HTTPException(
                status_code=400,
                detail=f"无效的分类，可选值: {', '.join(valid_categories)}"
            )
        
        # 验证指标
        valid_metrics = [
            "avg_length_hours", "max_length_hours", "min_length_hours",
            "topics_count", "topics_active", "topics_ended",
            "intensity_sum", "intensity_avg", "intensity_max",
            "heat_sum", "heat_avg"
        ]
        if metric not in valid_metrics:
            raise HTTPException(
                status_code=400,
                detail=f"无效的指标，可选值: {', '.join(valid_metrics)}"
            )
        
        # 计算日期范围
        end_date = now_cn().date()
        start_date = end_date - timedelta(days=days)
        
        # 查询数据
        stmt = (
            select(CategoryDayMetrics)
            .where(
                and_(
                    CategoryDayMetrics.category == category,
                    CategoryDayMetrics.day >= start_date,
                    CategoryDayMetrics.day <= end_date
                )
            )
            .order_by(CategoryDayMetrics.day)
        )
        
        result = await db.execute(stmt)
        metrics_list = result.scalars().all()
        
        # 构建时序数据
        data_points: List[TimeSeriesPoint] = []
        for m in metrics_list:
            # 动态获取指标值
            value = getattr(m, metric, 0)
            if value is None:
                value = 0.0
            
            data_points.append(
                TimeSeriesPoint(
                    date=m.day.strftime("%Y-%m-%d"),
                    value=float(value)
                )
            )
        
        return CategoryTimeSeriesResponse(
            category=category,
            metric=metric,
            data=data_points
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取时序数据失败: {str(e)}")

