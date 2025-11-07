"""
Echoman Backend Main Application

FastAPI 应用主入口
"""
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import settings
from app.api import api_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    # 启动时执行
    print(f"🚀 启动 {settings.app_name} v0.1.0")
    print(f"📝 环境: {settings.env}")
    print(f"🔧 调试模式: {settings.debug}")
    
    yield
    
    # 关闭时执行
    print("👋 关闭应用...")


# 创建 FastAPI 应用
app = FastAPI(
    title=settings.app_name,
    description="热点事件聚合与回声追踪系统",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url=f"{settings.api_v1_prefix}/openapi.json",
    lifespan=lifespan
)

# CORS 中间件
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# 健康检查端点
@app.get("/health")
async def health_check():
    """健康检查"""
    return JSONResponse(
        content={
            "status": "ok",
            "version": "0.1.0",
            "env": settings.env
        }
    )


# 注册 API 路由
app.include_router(api_router, prefix=settings.api_v1_prefix)


if __name__ == "__main__":
    import uvicorn
    
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.debug
    )

