"""
指标相关Schema定义
"""
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field


class HalfdayMergeMetrics(BaseModel):
    """半日归并指标"""
    last_merge_at: Optional[str] = Field(None, description="最后归并时间")
    period: str = Field(..., description="时段（AM|PM）")
    input_items: int = Field(..., description="输入条数")
    kept_items: int = Field(..., description="保留条数")
    dropped_items: int = Field(..., description="丢弃条数")
    keep_rate: float = Field(..., description="保留率")
    drop_rate: float = Field(..., description="丢弃率")
    merge_groups: int = Field(..., description="归并组数")
    avg_occurrence: float = Field(..., description="平均出现次数")


class GlobalMergeMetrics(BaseModel):
    """整体归并指标"""
    last_merge_at: Optional[str] = Field(None, description="最后归并时间")
    input_events: int = Field(..., description="输入事件数")
    merge_count: int = Field(..., description="归并数量")
    new_count: int = Field(..., description="新建数量")
    merge_rate: float = Field(..., description="归并率")


class IngestMetrics(BaseModel):
    """采集指标"""
    last_run: Dict[str, Any] = Field(..., description="最后运行信息")
    per_platform: List[Dict[str, Any]] = Field(..., description="各平台统计")
    halfday_merge: HalfdayMergeMetrics = Field(..., description="半日归并指标")
    global_merge: GlobalMergeMetrics = Field(..., description="整体归并指标")
    merge_reject_rate: float = Field(..., description="归并拒绝率")
    topics_total: int = Field(..., description="话题总数")
    topics_active: int = Field(..., description="活跃话题数")
    topics_ended: int = Field(..., description="已结束话题数")
    topics_new_per_day: float = Field(..., description="每日新增话题数")


class ChatMetrics(BaseModel):
    """对话指标"""
    citation_hit_rate: float = Field(..., description="引用命中率")
    latency_p95_ms: int = Field(..., description="P95延迟（毫秒）")
    timeout_rate: float = Field(..., description="超时率")
    failure_rate: float = Field(..., description="失败率")


class CostMetrics(BaseModel):
    """成本指标"""
    by_task: List[Dict[str, Any]] = Field(..., description="按任务统计")
    by_provider: List[Dict[str, Any]] = Field(..., description="按提供商统计")


class MetricsSummaryResponse(BaseModel):
    """指标汇总响应"""
    ingest: IngestMetrics = Field(..., description="采集指标")
    chat: ChatMetrics = Field(..., description="对话指标")
    cost: CostMetrics = Field(..., description="成本指标")


class CategoryMetricsItem(BaseModel):
    """分类指标项"""
    category: str = Field(..., description="分类")
    avg_length_hours: float = Field(..., description="平均回声时长（小时）")
    max_length_hours: float = Field(..., description="最长回声时长（小时）")
    min_length_hours: float = Field(..., description="最短回声时长（小时）")
    avg_length_display: str = Field(..., description="平均回声时长（人性化）")
    max_length_display: str = Field(..., description="最长回声时长（人性化）")
    min_length_display: str = Field(..., description="最短回声时长（人性化）")
    max_length_topic_id: Optional[int] = Field(None, description="最长回声话题ID")
    min_length_topic_id: Optional[int] = Field(None, description="最短回声话题ID")
    topics_count: int = Field(..., description="话题总数")
    intensity_sum: int = Field(..., description="强度总和")
    
    class Config:
        from_attributes = True


class CategoryMetricsResponse(BaseModel):
    """分类指标响应"""
    window_days: int = Field(..., description="统计窗口天数")
    ended_only: bool = Field(..., description="是否仅统计已结束话题")
    items: List[CategoryMetricsItem] = Field(..., description="分类指标列表")


class TimeSeriesPoint(BaseModel):
    """时序数据点"""
    date: str = Field(..., description="日期（YYYY-MM-DD）")
    value: float = Field(..., description="指标值")
    
    class Config:
        from_attributes = True


class CategoryTimeSeriesResponse(BaseModel):
    """分类时序数据响应"""
    category: str = Field(..., description="分类")
    metric: str = Field(..., description="指标名称")
    data: List[TimeSeriesPoint] = Field(..., description="时序数据点列表")


class AdminTimeSeriesResponse(BaseModel):
    """管理后台时序数据响应"""
    metric: str = Field(..., description="指标名称")
    data: List[TimeSeriesPoint] = Field(..., description="时序数据点列表")

