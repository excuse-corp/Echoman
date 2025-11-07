"""
采集原子项模型

对应文档中的 source_items 表
存储各平台采集的原始数据
"""
from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, Float, JSON, Text, Index, BigInteger
from sqlalchemy.dialects.postgresql import JSONB
from .base import Base
from app.utils.timezone import now_cn


class SourceItem(Base):
    """采集原子项"""
    
    __tablename__ = "source_items"
    
    # ========== 主键 ==========
    id = Column(BigInteger, primary_key=True, autoincrement=True, comment="主键ID")
    
    # ========== 基础字段 ==========
    platform = Column(
        String(20),
        nullable=False,
        index=True,
        comment="平台名称（weibo|zhihu|toutiao|sina|netease|baidu|hupu）"
    )
    title = Column(String(500), nullable=False, comment="标题")
    summary = Column(Text, nullable=True, comment="摘要/正文")
    url = Column(String(1000), nullable=False, comment="链接")
    
    # ========== 时间字段 ==========
    published_at = Column(DateTime, nullable=True, comment="发布时间")
    fetched_at = Column(DateTime, default=now_cn, nullable=False, comment="抓取时间")
    
    # ========== 互动与热度 ==========
    interactions = Column(JSONB, nullable=True, comment="互动信息（转/评/赞/阅/藏）")
    heat_value = Column(Float, nullable=True, comment="原始热度值（sina/hupu为null）")
    heat_normalized = Column(Float, nullable=True, comment="归并周期内归一化热度（0-1）")
    
    # ========== 去重字段 ==========
    url_hash = Column(String(64), nullable=False, index=True, comment="URL哈希（MD5）")
    content_hash = Column(String(64), nullable=False, index=True, comment="内容哈希（MD5）")
    dedup_key = Column(String(100), nullable=False, unique=True, comment="去重键")
    
    # ========== 归并相关 ==========
    period_merge_group_id = Column(String(50), nullable=True, index=True, comment="归并组ID")
    period = Column(String(20), nullable=True, index=True, comment="归并时段（如2025-10-29_AM/PM/EVE）")
    occurrence_count = Column(Integer, default=1, nullable=False, comment="归并周期内出现次数")
    merge_status = Column(
        String(30),
        default="pending_halfday_merge",
        nullable=False,
        index=True,
        comment="归并状态（pending_halfday_merge|pending_global_merge|merged|discarded）"
    )
    
    # ========== 向量关联 ==========
    embedding_id = Column(BigInteger, nullable=True, index=True, comment="向量ID（外键引用embeddings表）")
    
    # ========== 运行追踪 ==========
    run_id = Column(String(50), nullable=True, index=True, comment="采集运行ID")
    
    # ========== 索引定义 ==========
    __table_args__ = (
        Index("idx_platform_fetched_at", "platform", "fetched_at"),
        Index("idx_period_status", "period", "merge_status"),
        Index("idx_merge_group", "period_merge_group_id", "occurrence_count"),
        {"comment": "采集原子项表"}
    )
    
    def __repr__(self):
        return f"<SourceItem(id={self.id}, platform={self.platform}, title={self.title[:30]})>"

