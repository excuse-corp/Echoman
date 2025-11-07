"""
通用Schema定义
"""
from typing import Generic, TypeVar, Optional, List, Any
from pydantic import BaseModel, Field


class ErrorResponse(BaseModel):
    """错误响应"""
    code: str = Field(..., description="错误码")
    message: str = Field(..., description="错误消息")
    request_id: Optional[str] = Field(None, description="请求ID")
    
    class Config:
        json_schema_extra = {
            "example": {
                "code": "INVALID_ARGUMENT",
                "message": "参数缺失或非法",
                "request_id": "req_123456"
            }
        }


class PaginationParams(BaseModel):
    """分页参数"""
    page: int = Field(default=1, ge=1, description="页码")
    size: int = Field(default=20, ge=1, le=100, description="每页大小")


T = TypeVar('T')


class PaginatedResponse(BaseModel, Generic[T]):
    """分页响应"""
    page: int = Field(..., description="当前页码")
    size: int = Field(..., description="每页大小")
    total: int = Field(..., description="总记录数")
    items: List[T] = Field(..., description="数据列表")
    
    class Config:
        from_attributes = True


class HealthResponse(BaseModel):
    """健康检查响应"""
    status: str = Field(default="ok", description="状态")
    version: Optional[str] = Field(None, description="版本号")
    timestamp: Optional[str] = Field(None, description="时间戳")

