"""
主题/事件模型

对应文档中的 topics、topic_nodes、topic_halfday_heat 表
"""
from datetime import datetime
from app.utils.timezone import now_cn
from sqlalchemy import (
    Column, Integer, String, DateTime, Float, Text, 
    ForeignKey, Index, BigInteger, Date, UniqueConstraint
)
from sqlalchemy.orm import relationship
from .base import Base


class Topic(Base):
    """主题/事件"""
    
    __tablename__ = "topics"
    
    # ========== 主键 ==========
    id = Column(BigInteger, primary_key=True, autoincrement=True, comment="主键ID")
    
    # ========== 基础字段 ==========
    title_key = Column(String(500), nullable=False, comment="标题归并键")
    
    # ========== 时间字段 ==========
    first_seen = Column(DateTime, nullable=False, index=True, comment="首次发现时间")
    last_active = Column(DateTime, nullable=False, index=True, comment="最后活跃时间")
    
    # ========== 状态字段 ==========
    status = Column(
        String(20),
        default="active",
        nullable=False,
        index=True,
        comment="状态（active|ended）"
    )
    
    # ========== 回声指标 ==========
    intensity_total = Column(Integer, default=0, nullable=False, comment="强度总量（覆盖量累加）")
    interaction_total = Column(BigInteger, default=0, nullable=True, comment="互动总量（可选维度）")
    
    # ========== 热度字段 ==========
    current_heat_normalized = Column(Float, nullable=True, comment="当前归一化热度（最新半日）")
    heat_percentage = Column(Float, nullable=True, comment="当前热度占比（%）")
    
    # ========== 摘要关联 ==========
    summary_id = Column(BigInteger, nullable=True, comment="当前主题摘要快照ID（外键）")
    
    # ========== 分类字段 ==========
    category = Column(
        String(50),
        nullable=True,
        index=True,
        comment="分类（entertainment|current_affairs|sports_esports）"
    )
    category_confidence = Column(Float, nullable=True, comment="分类置信度（0-1）")
    category_method = Column(
        String(20),
        nullable=True,
        comment="分类方法（llm|heuristic|manual）"
    )
    category_updated_at = Column(DateTime, nullable=True, comment="分类更新时间")
    
    # ========== 关系定义 ==========
    nodes = relationship("TopicNode", back_populates="topic", cascade="all, delete-orphan")
    period_heats = relationship("TopicPeriodHeat", back_populates="topic", cascade="all, delete-orphan")
    
    # ========== 索引定义 ==========
    __table_args__ = (
        Index("idx_status_last_active", "status", "last_active"),
        Index("idx_category_status", "category", "status"),
        Index("idx_heat_normalized", "current_heat_normalized"),
        {"comment": "主题/事件表"}
    )
    
    def __repr__(self):
        return f"<Topic(id={self.id}, title={self.title_key[:30]}, status={self.status})>"


class TopicNode(Base):
    """主题时间线节点"""
    
    __tablename__ = "topic_nodes"
    
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
    source_item_id = Column(
        BigInteger,
        ForeignKey("source_items.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="源数据项ID"
    )
    
    # ========== 追加信息 ==========
    appended_at = Column(DateTime, default=now_cn, nullable=False, comment="追加时间")
    delta_interactions = Column(Integer, default=0, nullable=True, comment="新增互动量（累加入topic）")
    
    # ========== 关系定义 ==========
    topic = relationship("Topic", back_populates="nodes")
    source_item = relationship("SourceItem", foreign_keys=[source_item_id])
    
    # ========== 索引定义 ==========
    __table_args__ = (
        Index("idx_topic_appended", "topic_id", "appended_at"),
        UniqueConstraint("topic_id", "source_item_id", name="uq_topic_source"),
        {"comment": "主题时间线节点表"}
    )
    
    def __repr__(self):
        return f"<TopicNode(id={self.id}, topic_id={self.topic_id}, source_item_id={self.source_item_id})>"


class TopicPeriodHeat(Base):
    """主题归并周期热度记录（AM/PM/EVE）"""
    
    __tablename__ = "topic_period_heat"
    
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
    
    # ========== 时间字段 ==========
    date = Column(Date, nullable=False, index=True, comment="日期")
    period = Column(String(10), nullable=False, comment="时段（AM|PM|EVE）")
    
    # ========== 热度字段 ==========
    heat_normalized = Column(Float, nullable=False, comment="归并周期内归一化热度（0-1）")
    heat_percentage = Column(Float, nullable=False, comment="占归并周期总热度百分比")
    source_count = Column(Integer, default=0, nullable=False, comment="归并周期内的source_item数量")
    
    # ========== 关系定义 ==========
    topic = relationship("Topic", back_populates="period_heats")
    
    # ========== 索引定义 ==========
    __table_args__ = (
        Index("idx_topic_date_period", "topic_id", "date", "period"),
        UniqueConstraint("topic_id", "date", "period", name="uq_topic_date_period"),
        {"comment": "主题归并周期热度记录表"}
    )
    
    def __repr__(self):
        return f"<TopicPeriodHeat(id={self.id}, topic_id={self.topic_id}, date={self.date}, period={self.period})>"

