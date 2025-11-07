"""
摘要快照模型

对应文档中的 summaries 表
存储主题的摘要快照
"""
from datetime import datetime
from app.utils.timezone import now_cn
from sqlalchemy import Column, String, Text, DateTime, BigInteger, ForeignKey, Index
from .base import Base


class Summary(Base):
    """摘要快照"""
    
    __tablename__ = "summaries"
    
    # ========== 主键 ==========
    id = Column(BigInteger, primary_key=True, autoincrement=True, comment="主键ID")
    
    # ========== 外键关联 ==========
    topic_id = Column(
        BigInteger,
        ForeignKey("topics.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="主题ID"
    )
    
    # ========== 摘要内容 ==========
    content = Column(Text, nullable=False, comment="摘要内容")
    
    # ========== 生成方法 ==========
    method = Column(
        String(20),
        nullable=False,
        comment="生成方法（full|incremental）"
    )
    
    # ========== 生成时间 ==========
    generated_at = Column(DateTime, default=now_cn, nullable=False, comment="生成时间")
    
    # ========== 模型信息 ==========
    provider = Column(String(50), nullable=True, comment="LLM提供商")
    model = Column(String(100), nullable=True, comment="LLM模型名称")
    
    # ========== 索引定义 ==========
    __table_args__ = (
        Index("idx_topic_generated", "topic_id", "generated_at"),
        {"comment": "摘要快照表"}
    )
    
    def __repr__(self):
        return f"<Summary(id={self.id}, topic_id={self.topic_id}, method={self.method})>"

