"""
采集相关API路由
"""
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import get_db
from app.schemas.ingest import (
    IngestRunRequest,
    IngestRunResponse,
    IngestStatusResponse,
    RunsHistoryResponse
)
from app.services.ingestion import IngestionService

router = APIRouter()


@router.post("/run", response_model=IngestRunResponse)
async def trigger_ingestion(
    request: IngestRunRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    手动触发采集任务
    
    - **platforms**: 平台列表（不填则全部）
    - **limit**: 每平台采集条数
    """
    service = IngestionService(db)
    
    try:
        result = await service.run_ingestion(
            platforms=request.platforms,
            limit=request.limit
        )
        
        return IngestRunResponse(
            run_id=result["run_id"],
            scheduled=True,
            message=f"采集任务已提交，运行ID: {result['run_id']}"
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/runs", response_model=RunsHistoryResponse)
async def get_runs_history(
    limit: int = 20,
    db: AsyncSession = Depends(get_db)
):
    """
    获取最近的采集运行历史
    
    - **limit**: 返回条数（默认20）
    """
    service = IngestionService(db)
    
    try:
        runs = await service.get_runs_history(limit=limit)
        
        items = [
            {
                "run_id": run.run_id,
                "start_at": run.started_at,
                "end_at": run.ended_at,
                "status": run.status,
                "total": run.total_items,
                "success": run.success_items,
                "failed": run.failed_items,
                "parse_success_rate": run.parse_success_rate
            }
            for run in runs
        ]
        
        return RunsHistoryResponse(items=items)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/sources/status", response_model=IngestStatusResponse)
async def get_sources_status(
    db: AsyncSession = Depends(get_db)
):
    """
    获取各平台连接器健康状况
    
    返回各平台的成功率、延迟、最后运行时间等信息
    """
    service = IngestionService(db)
    
    try:
        items = await service.get_platform_status()
        return IngestStatusResponse(items=items)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

