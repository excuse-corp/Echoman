"""API 路由模块"""
from fastapi import APIRouter
from .v1 import ingest, topics, admin, chat, categories

# 创建主路由
api_router = APIRouter()

# 注册子路由
api_router.include_router(ingest.router, prefix="/ingest", tags=["采集"])
api_router.include_router(topics.router, prefix="/topics", tags=["话题"])
api_router.include_router(categories.router, prefix="/categories", tags=["分类"])
api_router.include_router(admin.router, prefix="/admin", tags=["管理"])
api_router.include_router(chat.router, prefix="/chat", tags=["对话"])

__all__ = ["api_router"]
