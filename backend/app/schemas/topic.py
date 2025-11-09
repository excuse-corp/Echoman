"""
话题相关Schema定义
"""
from datetime import datetime, date
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field


class TopicResponse(BaseModel):
    """话题响应"""
    id: int = Field(..., description="话题ID")
    title_key: str = Field(..., description="标题")
    first_seen: datetime = Field(..., description="首次发现时间")
    last_active: datetime = Field(..., description="最后活跃时间")
    status: str = Field(..., description="状态（active|ended）")
    category: Optional[str] = Field(None, description="分类")
    intensity_total: int = Field(..., description="强度总量")
    interaction_total: Optional[int] = Field(None, description="互动总量")
    current_heat_normalized: Optional[float] = Field(None, description="当前归一化热度")
    heat_percentage: Optional[float] = Field(None, description="当前热度占比")
    
    class Config:
        from_attributes = True


class SummaryResponse(BaseModel):
    """摘要响应"""
    id: int = Field(..., description="摘要ID")
    content: str = Field(..., description="摘要内容")
    updated_at: datetime = Field(..., description="更新时间")
    method: str = Field(..., description="生成方法")
    
    class Config:
        from_attributes = True


class TopicDetailResponse(TopicResponse):
    """话题详情响应"""
    length_display: str = Field(..., description="回声时长（人性化显示）")
    summary: Optional[SummaryResponse] = Field(None, description="当前摘要")


class TimelineNodeResponse(BaseModel):
    """时间线节点响应"""
    node_id: int = Field(..., description="节点ID")
    topic_id: int = Field(..., description="话题ID")
    timestamp: datetime = Field(..., description="时间戳")
    title: str = Field(..., description="标题")
    content: str = Field(..., description="内容摘要")
    source_platform: str = Field(..., description="来源平台")
    source_url: str = Field(..., description="原文链接")
    captured_at: datetime = Field(..., description="采集时间")
    engagement: Optional[int] = Field(None, description="互动数")
    # 聚合字段（用于相同内容的多次报道）
    duplicate_count: Optional[int] = Field(None, description="重复报道次数")
    time_range_start: Optional[datetime] = Field(None, description="时间范围开始")
    time_range_end: Optional[datetime] = Field(None, description="时间范围结束")
    all_platforms: Optional[List[str]] = Field(None, description="所有报道平台列表")
    all_source_urls: Optional[List[str]] = Field(None, description="所有原文链接")
    all_timestamps: Optional[List[datetime]] = Field(None, description="所有原文对应的时间戳")
    
    class Config:
        from_attributes = True


class TopicTimelineResponse(BaseModel):
    """话题时间线响应"""
    topic_summary: Optional[str] = Field(None, description="话题摘要")
    items: List[TimelineNodeResponse] = Field(..., description="时间线节点列表")


class HeatTrendItem(BaseModel):
    """热度趋势项"""
    date: str = Field(..., description="日期（YYYY-MM-DD）")
    period: str = Field(..., description="时段（AM|PM）")
    heat_normalized: float = Field(..., description="归一化热度")
    heat_percentage: float = Field(..., description="热度占比（%）")
    source_count: int = Field(..., description="源数据数量")
    timestamp: datetime = Field(..., description="时间戳")
    
    class Config:
        from_attributes = True


class TopicHeatTrendResponse(BaseModel):
    """话题热度趋势响应"""
    topic_id: int = Field(..., description="话题ID")
    items: List[HeatTrendItem] = Field(..., description="热度趋势列表")

