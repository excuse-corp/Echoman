"""
LLM判定记录模型

对应文档中的 llm_judgements 表
存储所有LLM调用的请求与响应
"""
from datetime import datetime
from app.utils.timezone import now_cn
from sqlalchemy import Column, Integer, String, Text, DateTime, BigInteger, Index
from sqlalchemy.dialects.postgresql import JSONB
from .base import Base


class LLMJudgement(Base):
    """LLM判定任务"""
    
    __tablename__ = "llm_judgements"
    
    # ========== 主键 ==========
    id = Column(BigInteger, primary_key=True, autoincrement=True, comment="主键ID")
    
    # ========== 任务类型 ==========
    type = Column(
        String(50),
        nullable=False,
        index=True,
        comment="类型（merge|summarize|chat_rerank|classify等）"
    )
    
    # ========== 状态 ==========
    status = Column(
        String(20),
        default="pending",
        nullable=False,
        index=True,
        comment="状态（pending|success|failed|timeout）"
    )
    
    # ========== 请求与响应 ==========
    request = Column(JSONB, nullable=False, comment="请求内容（JSON）")
    response = Column(JSONB, nullable=True, comment="响应内容（JSON）")
    error_message = Column(Text, nullable=True, comment="错误信息")
    
    # ========== 性能指标 ==========
    latency_ms = Column(Integer, nullable=True, comment="延迟（毫秒）")
    tokens_prompt = Column(Integer, nullable=True, comment="Prompt Token数")
    tokens_completion = Column(Integer, nullable=True, comment="Completion Token数")
    
    # ========== 模型信息 ==========
    provider = Column(String(50), nullable=False, comment="提供商（openai|qwen|azure等）")
    model = Column(String(100), nullable=False, comment="模型名称")
    
    # ========== 时间字段 ==========
    started_at = Column(DateTime, default=now_cn, nullable=False, comment="开始时间")
    completed_at = Column(DateTime, nullable=True, comment="完成时间")
    
    # ========== 索引定义 ==========
    __table_args__ = (
        Index("idx_type_status", "type", "status"),
        Index("idx_provider_created", "provider", "created_at"),
        {"comment": "LLM判定任务表"}
    )
    
    def __repr__(self):
        return f"<LLMJudgement(id={self.id}, type={self.type}, status={self.status})>"

