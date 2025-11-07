"""
数据库基础模型
"""
from datetime import datetime
from sqlalchemy import Column, DateTime
from sqlalchemy.orm import declarative_base, declared_attr
from app.utils.timezone import now_cn


class BaseModel:
    """所有模型的基类（使用中国时区）"""
    
    @declared_attr
    def __tablename__(cls) -> str:
        """自动生成表名（蛇形命名）"""
        import re
        name = cls.__name__
        # 将驼峰命名转为蛇形命名
        name = re.sub('(.)([A-Z][a-z]+)', r'\1_\2', name)
        name = re.sub('([a-z0-9])([A-Z])', r'\1_\2', name).lower()
        return name
    
    created_at = Column(DateTime, default=now_cn, nullable=False, comment="创建时间")
    updated_at = Column(DateTime, default=now_cn, onupdate=now_cn, nullable=False, comment="更新时间")


# 创建声明式基类
Base = declarative_base(cls=BaseModel)

