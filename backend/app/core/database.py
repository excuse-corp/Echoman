"""
数据库连接与会话管理
"""
from typing import AsyncGenerator, Optional
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker, AsyncEngine
from sqlalchemy.pool import NullPool
from app.config import settings


# 全局引擎和会话工厂（主进程）
_engine: Optional[AsyncEngine] = None
_async_session: Optional[async_sessionmaker] = None


def get_engine() -> AsyncEngine:
    """
    获取数据库引擎（线程安全）
    
    在Celery worker子进程中会重新创建引擎，避免event loop冲突
    """
    global _engine
    if _engine is None:
        _engine = create_async_engine(
            settings.database_url,
            echo=settings.debug,
            poolclass=NullPool if settings.env == "test" else None,
            pool_pre_ping=True,
            pool_size=10,
            max_overflow=20,
        )
    return _engine


def get_async_session() -> async_sessionmaker:
    """
    获取异步会话工厂（线程安全）
    
    在Celery worker子进程中会重新创建会话工厂，避免event loop冲突
    """
    global _async_session
    if _async_session is None:
        _async_session = async_sessionmaker(
            get_engine(),
            class_=AsyncSession,
            expire_on_commit=False,
            autocommit=False,
            autoflush=False,
        )
    return _async_session


def reset_db_engine():
    """
    重置数据库引擎和会话工厂
    
    用于Celery worker子进程初始化，确保在新的event loop中创建连接
    """
    global _engine, _async_session
    
    # 关闭旧引擎（如果存在）
    if _engine is not None:
        try:
            # 同步关闭（在子进程中，旧的loop已经不可用）
            _engine.sync_engine.dispose()
        except Exception:
            pass
        _engine = None
    
    # 清空会话工厂
    _async_session = None


# 为了向后兼容，保留全局对象
# engine 现在通过 get_engine() 函数获取
# async_session 现在通过 get_async_session() 函数获取
engine = get_engine()  # 会在首次调用时创建
async_session = get_async_session  # 函数引用，调用时返回session工厂


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    获取数据库会话依赖
    
    用于FastAPI依赖注入
    """
    session_maker = get_async_session()
    async with session_maker() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()

