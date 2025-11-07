"""
管理相关API路由
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, cast, Date
from typing import List
from datetime import datetime, timedelta

from app.core import get_db
from app.models import Topic, RunIngest
from app.schemas.metrics import TimeSeriesPoint, AdminTimeSeriesResponse
from app.utils.timezone import now_cn

router = APIRouter()


@router.get("/metrics/summary")
async def get_metrics_summary(
    db: AsyncSession = Depends(get_db)
):
    """
    获取系统指标汇总
    
    包含采集情况、话题统计、归并指标、对话指标、成本指标等
    """
    try:
        # 获取最后一次采集运行
        stmt = select(RunIngest).order_by(RunIngest.started_at.desc()).limit(1)
        result = await db.execute(stmt)
        last_run = result.scalar_one_or_none()
        
        # 获取话题统计
        stmt_total = select(func.count(Topic.id))
        stmt_active = select(func.count(Topic.id)).where(Topic.status == "active")
        stmt_ended = select(func.count(Topic.id)).where(Topic.status == "ended")
        
        total = (await db.execute(stmt_total)).scalar()
        active = (await db.execute(stmt_active)).scalar()
        ended = (await db.execute(stmt_ended)).scalar()
        
        return {
            "ingest": {
                "last_run": {
                    "run_id": last_run.run_id if last_run else None,
                    "status": last_run.status if last_run else None,
                    "start_at": last_run.started_at if last_run else None,
                    "end_at": last_run.ended_at if last_run else None,
                    "duration_ms": last_run.duration_ms if last_run else None
                },
                "per_platform": last_run.platform_results if last_run else [],
                "halfday_merge": {
                    "last_merge_at": None,
                    "period": "PM",
                    "input_items": 0,
                    "kept_items": 0,
                    "dropped_items": 0,
                    "keep_rate": 0.0,
                    "drop_rate": 0.0,
                    "merge_groups": 0,
                    "avg_occurrence": 0.0
                },
                "global_merge": {
                    "last_merge_at": None,
                    "input_events": 0,
                    "merge_count": 0,
                    "new_count": 0,
                    "merge_rate": 0.0
                },
                "merge_reject_rate": 0.0,
                "topics_total": total,
                "topics_active": active,
                "topics_ended": ended,
                "topics_new_per_day": 0.0
            },
            "chat": {
                "citation_hit_rate": 0.0,
                "latency_p95_ms": 0,
                "timeout_rate": 0.0,
                "failure_rate": 0.0
            },
            "cost": {
                "by_task": [],
                "by_provider": []
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/categories")
async def get_categories():
    """
    获取分类列表
    """
    return {
        "items": [
            {"key": "entertainment", "display": "娱乐八卦类"},
            {"key": "current_affairs", "display": "社会时事类"},
            {"key": "sports_esports", "display": "体育电竞类"}
        ]
    }


@router.get("/metrics/timeseries", response_model=AdminTimeSeriesResponse)
async def get_admin_metrics_timeseries(
    metric: str = Query(..., description="指标名称"),
    days: int = Query(30, ge=1, le=365, description="查询天数，默认30天"),
    db: AsyncSession = Depends(get_db)
):
    """
    获取管理后台指标时序数据
    
    用于展示系统级别的指标趋势图
    
    Args:
        metric: 指标名称，可选值：
            - topics_new_per_day: 每日新增话题数
            - topics_total_per_day: 每日话题总数
            - topics_active_per_day: 每日活跃话题数
            - topics_ended_per_day: 每日已结束话题数
        days: 查询天数
        
    Returns:
        时序数据列表
    """
    try:
        # 验证指标
        valid_metrics = [
            "topics_new_per_day",
            "topics_total_per_day",
            "topics_active_per_day",
            "topics_ended_per_day"
        ]
        if metric not in valid_metrics:
            raise HTTPException(
                status_code=400,
                detail=f"无效的指标，可选值: {', '.join(valid_metrics)}"
            )
        
        # 计算日期范围
        end_date = now_cn().date()
        start_date = end_date - timedelta(days=days - 1)  # 包含今天
        
        data_points: List[TimeSeriesPoint] = []
        
        if metric == "topics_new_per_day":
            # 每日新增话题数（按 first_seen 分组）
            stmt = (
                select(
                    cast(Topic.first_seen, Date).label('date'),
                    func.count(Topic.id).label('count')
                )
                .where(cast(Topic.first_seen, Date) >= start_date)
                .where(cast(Topic.first_seen, Date) <= end_date)
                .group_by(cast(Topic.first_seen, Date))
                .order_by(cast(Topic.first_seen, Date))
            )
            result = await db.execute(stmt)
            rows = result.all()
            
            for row in rows:
                data_points.append(
                    TimeSeriesPoint(
                        date=row.date.strftime("%Y-%m-%d"),
                        value=float(row.count)
                    )
                )
        
        elif metric == "topics_total_per_day":
            # 每日话题总数（累计）
            # 对于每一天，统计 first_seen <= 该天 的所有 Topic
            current_date = start_date
            while current_date <= end_date:
                stmt = select(func.count(Topic.id)).where(
                    cast(Topic.first_seen, Date) <= current_date
                )
                result = await db.execute(stmt)
                count = result.scalar()
                
                data_points.append(
                    TimeSeriesPoint(
                        date=current_date.strftime("%Y-%m-%d"),
                        value=float(count)
                    )
                )
                current_date += timedelta(days=1)
        
        elif metric == "topics_active_per_day":
            # 每日活跃话题数
            # 对于每一天，统计 status='active' 且 last_active >= 该天 - 1天 的 Topic
            current_date = start_date
            while current_date <= end_date:
                stmt = select(func.count(Topic.id)).where(
                    Topic.status == "active",
                    cast(Topic.last_active, Date) >= current_date - timedelta(days=1)
                )
                result = await db.execute(stmt)
                count = result.scalar()
                
                data_points.append(
                    TimeSeriesPoint(
                        date=current_date.strftime("%Y-%m-%d"),
                        value=float(count)
                    )
                )
                current_date += timedelta(days=1)
        
        elif metric == "topics_ended_per_day":
            # 每日已结束话题数（按 last_active 分组）
            stmt = (
                select(
                    cast(Topic.last_active, Date).label('date'),
                    func.count(Topic.id).label('count')
                )
                .where(Topic.status == "ended")
                .where(cast(Topic.last_active, Date) >= start_date)
                .where(cast(Topic.last_active, Date) <= end_date)
                .group_by(cast(Topic.last_active, Date))
                .order_by(cast(Topic.last_active, Date))
            )
            result = await db.execute(stmt)
            rows = result.all()
            
            for row in rows:
                data_points.append(
                    TimeSeriesPoint(
                        date=row.date.strftime("%Y-%m-%d"),
                        value=float(row.count)
                    )
                )
        
        return AdminTimeSeriesResponse(
            metric=metric,
            data=data_points
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取时序数据失败: {str(e)}")

