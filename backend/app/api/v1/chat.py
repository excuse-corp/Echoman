"""
对话API

提供RAG对话功能（支持非流式和SSE流式）
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional
from pydantic import BaseModel
import json
import asyncio

from app.core import get_db
from app.services.rag_service import RAGService
from app.utils.timezone import now_cn


router = APIRouter(tags=["Chat"])


# ========== 请求/响应模型 ==========

class AskRequest(BaseModel):
    """提问请求"""
    query: str
    mode: str = "global"  # "topic" 或 "global"
    topic_id: Optional[int] = None
    chat_id: Optional[int] = None
    stream: bool = False  # 是否使用流式输出


class Citation(BaseModel):
    """引用"""
    topic_id: Optional[int]
    node_id: Optional[int]
    source_url: str
    snippet: str
    platform: str


class Diagnostics(BaseModel):
    """诊断信息"""
    latency_ms: int
    tokens_prompt: int
    tokens_completion: int
    context_chunks: int
    fallback: bool = False


class AskResponse(BaseModel):
    """回答响应"""
    answer: str
    citations: list[Citation]
    diagnostics: Diagnostics


class CreateChatRequest(BaseModel):
    """创建会话请求"""
    mode: str = "global"
    topic_id: Optional[int] = None


class ChatInfo(BaseModel):
    """会话信息"""
    id: int
    mode: str
    topic_id: Optional[int]
    created_at: str


# ========== API端点 ==========

@router.post("/ask")
async def ask_question(
    request: AskRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    提出问题
    
    支持两种模式：
    - topic: 基于特定主题的对话（需要提供topic_id）
    - global: 全局检索回答（无需topic_id）
    
    支持流式输出：
    - stream=false: 返回完整JSON响应
    - stream=true: 返回SSE事件流
    """
    rag_service = RAGService()
    
    try:
        # 如果请求流式输出
        if request.stream:
            return await _stream_chat_response(
                rag_service=rag_service,
                db=db,
                query=request.query,
                mode=request.mode,
                topic_id=request.topic_id,
                chat_id=request.chat_id
            )
        
        # 非流式：返回完整响应
        result = await rag_service.ask(
            db=db,
            query=request.query,
            mode=request.mode,
            topic_id=request.topic_id,
            chat_id=request.chat_id
        )
        
        return AskResponse(**result)
        
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"对话处理失败: {str(e)}")


@router.post("/create", response_model=ChatInfo)
async def create_chat(
    request: CreateChatRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    创建新会话
    """
    rag_service = RAGService()
    
    try:
        chat = await rag_service.create_chat(
            db=db,
            mode=request.mode,
            topic_id=request.topic_id
        )
        
        return ChatInfo(
            id=chat.id,
            mode=chat.mode,
            topic_id=chat.topic_id,
            created_at=chat.created_at.isoformat() if chat.created_at else now_cn().isoformat()
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"创建会话失败: {str(e)}")


async def _stream_chat_response(
    rag_service: RAGService,
    db: AsyncSession,
    query: str,
    mode: str,
    topic_id: Optional[int],
    chat_id: Optional[int]
):
    """
    SSE流式响应生成器
    
    事件类型：
    - token: 逐字输出
    - citations: 引用来源
    - done: 完成信号（包含诊断信息）
    - error: 错误信息
    """
    async def generate():
        try:
            # 调用流式RAG服务
            async for event in rag_service.ask_stream(
                db=db,
                query=query,
                mode=mode,
                topic_id=topic_id,
                chat_id=chat_id
            ):
                event_type = event.get("type")
                data = event.get("data", {})
                
                # 构造SSE格式
                # event: <type>\ndata: <json>\n\n
                sse_message = f"event: {event_type}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"
                yield sse_message
                
                # 避免发送过快
                await asyncio.sleep(0.01)
        
        except Exception as e:
            # 发送错误事件
            error_message = f"event: error\ndata: {json.dumps({'message': str(e)}, ensure_ascii=False)}\n\n"
            yield error_message
    
    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # 禁用nginx缓冲
        }
    )


@router.get("/health")
async def chat_health():
    """健康检查"""
    return {"status": "ok", "service": "chat"}

