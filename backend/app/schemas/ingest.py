"""
采集相关Schema定义
"""
from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field


class IngestRunRequest(BaseModel):
    """采集运行请求"""
    platforms: Optional[List[str]] = Field(None, description="平台列表（不填则全部）")
    limit: int = Field(default=30, ge=1, le=100, description="每平台采集条数")
    
    class Config:
        json_schema_extra = {
            "example": {
                "platforms": ["weibo", "zhihu"],
                "limit": 30
            }
        }


class IngestRunResponse(BaseModel):
    """采集运行响应"""
    run_id: str = Field(..., description="运行ID")
    scheduled: bool = Field(..., description="是否已调度")
    message: str = Field(default="采集任务已提交", description="提示消息")


class PlatformStatusResponse(BaseModel):
    """平台状态响应"""
    platform: str = Field(..., description="平台名称")
    last_success_at: Optional[datetime] = Field(None, description="最后成功时间")
    last_error: Optional[str] = Field(None, description="最后错误")
    success_rate_24h: float = Field(..., description="24小时成功率")
    avg_latency_ms: int = Field(..., description="平均延迟（毫秒）")
    records_per_run: int = Field(..., description="每次运行记录数")
    auth_mode: str = Field(..., description="认证模式")
    notes: Optional[str] = Field(None, description="备注")
    
    class Config:
        json_schema_extra = {
            "example": {
                "platform": "weibo",
                "last_success_at": "2025-05-10T02:01:24Z",
                "last_error": None,
                "success_rate_24h": 0.97,
                "avg_latency_ms": 820,
                "records_per_run": 30,
                "auth_mode": "cookie",
                "notes": "使用 hotSearch 接口"
            }
        }


class IngestStatusResponse(BaseModel):
    """采集状态响应"""
    items: List[PlatformStatusResponse] = Field(..., description="各平台状态列表")


class RunHistoryItem(BaseModel):
    """运行历史项"""
    run_id: str = Field(..., description="运行ID")
    start_at: datetime = Field(..., description="开始时间")
    end_at: Optional[datetime] = Field(None, description="结束时间")
    status: str = Field(..., description="状态")
    total: int = Field(..., description="总数")
    success: int = Field(..., description="成功数")
    failed: int = Field(..., description="失败数")
    parse_success_rate: float = Field(..., description="解析成功率")
    
    class Config:
        from_attributes = True


class RunsHistoryResponse(BaseModel):
    """运行历史响应"""
    items: List[RunHistoryItem] = Field(..., description="运行历史列表")

