"""
对话相关Schema定义
"""
from enum import Enum
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field


class ChatMode(str, Enum):
    """对话模式"""
    TOPIC = "topic"
    GLOBAL = "global"


class ChatRequest(BaseModel):
    """对话请求"""
    chat_mode: ChatMode = Field(..., description="对话模式（topic|global）")
    topic_id: Optional[int] = Field(None, description="话题ID（topic模式必填）")
    query: str = Field(..., description="用户问题", min_length=1, max_length=500)
    top_k: int = Field(default=5, ge=1, le=20, description="召回TopK")
    stream: bool = Field(default=False, description="是否流式返回")
    
    class Config:
        json_schema_extra = {
            "example": {
                "chat_mode": "topic",
                "topic_id": 123,
                "query": "这个事件的最新进展是什么？",
                "top_k": 5,
                "stream": False
            }
        }


class CitationResponse(BaseModel):
    """引用响应"""
    topic_id: Optional[int] = Field(None, description="话题ID")
    node_id: Optional[int] = Field(None, description="节点ID")
    source_url: Optional[str] = Field(None, description="源链接")
    snippet: Optional[str] = Field(None, description="引用片段")
    
    class Config:
        from_attributes = True


class DiagnosticsResponse(BaseModel):
    """诊断信息响应"""
    latency_ms: int = Field(..., description="延迟（毫秒）")
    tokens_prompt: Optional[int] = Field(None, description="Prompt Token数")
    tokens_completion: Optional[int] = Field(None, description="Completion Token数")
    provider: str = Field(..., description="LLM提供商")
    model: str = Field(..., description="模型名称")


class ChatResponse(BaseModel):
    """对话响应"""
    message_id: int = Field(..., description="消息ID")
    answer: str = Field(..., description="回答内容")
    citations: List[CitationResponse] = Field(..., description="引用列表")
    diagnostics: DiagnosticsResponse = Field(..., description="诊断信息")
    fallback: Optional[str] = Field(None, description="降级消息（证据不足时）")
    
    class Config:
        json_schema_extra = {
            "example": {
                "message_id": 456,
                "answer": "根据最新报道...",
                "citations": [
                    {
                        "topic_id": 123,
                        "node_id": 789,
                        "source_url": "https://...",
                        "snippet": "..."
                    }
                ],
                "diagnostics": {
                    "latency_ms": 1520,
                    "tokens_prompt": 1200,
                    "tokens_completion": 180,
                    "provider": "qwen",
                    "model": "qwen3-32b"
                },
                "fallback": None
            }
        }

