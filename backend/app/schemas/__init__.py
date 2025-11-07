"""Pydantic模式定义"""
from .common import ErrorResponse, PaginationParams, PaginatedResponse
from .topic import TopicResponse, TopicDetailResponse, TopicTimelineResponse, TopicHeatTrendResponse
from .chat import ChatRequest, ChatResponse, ChatMode
from .ingest import IngestRunRequest, IngestRunResponse, IngestStatusResponse
from .metrics import MetricsSummaryResponse, CategoryMetricsResponse

__all__ = [
    # Common
    "ErrorResponse",
    "PaginationParams",
    "PaginatedResponse",
    # Topic
    "TopicResponse",
    "TopicDetailResponse",
    "TopicTimelineResponse",
    "TopicHeatTrendResponse",
    # Chat
    "ChatRequest",
    "ChatResponse",
    "ChatMode",
    # Ingest
    "IngestRunRequest",
    "IngestRunResponse",
    "IngestStatusResponse",
    # Metrics
    "MetricsSummaryResponse",
    "CategoryMetricsResponse",
]

