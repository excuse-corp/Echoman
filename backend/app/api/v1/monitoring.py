"""
监控API

提供Prometheus指标、健康检查和系统状态
"""
from fastapi import APIRouter, Depends, Response
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Dict, Any

from app.core import get_db
from app.services.monitoring_service import monitoring_service


router = APIRouter(prefix="/monitoring", tags=["Monitoring"])


@router.get("/health")
async def health_check(db: AsyncSession = Depends(get_db)) -> Dict[str, Any]:
    """
    健康检查
    
    返回系统各组件的健康状态
    """
    return await monitoring_service.get_health_status(db)


@router.get("/metrics")
async def prometheus_metrics():
    """
    Prometheus指标端点
    
    返回Prometheus格式的指标数据
    """
    metrics, content_type = monitoring_service.get_prometheus_metrics()
    return Response(content=metrics, media_type=content_type)


@router.get("/metrics/summary")
async def metrics_summary(db: AsyncSession = Depends(get_db)) -> Dict[str, Any]:
    """
    指标摘要
    
    返回最近24小时的指标统计
    """
    return await monitoring_service.get_metrics_summary(db)


@router.post("/metrics/update")
async def update_metrics(db: AsyncSession = Depends(get_db)):
    """
    手动更新指标
    
    触发一次指标更新（通常由定时任务调用）
    """
    await monitoring_service.update_metrics(db)
    return {"status": "ok", "message": "指标已更新"}

