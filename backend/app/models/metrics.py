"""
指标聚合模型

对应文档中的 category_day_metrics 表
用于分类统计和聚合指标
"""
from sqlalchemy import Column, Integer, String, Float, Date, BigInteger, Index, UniqueConstraint
from .base import Base


class CategoryDayMetrics(Base):
    """分类按日聚合指标"""
    
    __tablename__ = "category_day_metrics"
    
    # ========== 主键 ==========
    id = Column(BigInteger, primary_key=True, autoincrement=True, comment="主键ID")
    
    # ========== 维度字段 ==========
    day = Column(Date, nullable=False, index=True, comment="日期")
    category = Column(
        String(50),
        nullable=False,
        index=True,
        comment="分类（entertainment|current_affairs|sports_esports）"
    )
    
    # ========== 话题统计 ==========
    topics_count = Column(Integer, default=0, nullable=False, comment="话题总数")
    topics_active = Column(Integer, default=0, nullable=False, comment="活跃话题数")
    topics_ended = Column(Integer, default=0, nullable=False, comment="已结束话题数")
    
    # ========== 回声时长统计 ==========
    avg_length_hours = Column(Float, nullable=True, comment="平均回声时长（小时）")
    max_length_hours = Column(Float, nullable=True, comment="最长回声时长（小时）")
    min_length_hours = Column(Float, nullable=True, comment="最短回声时长（小时）")
    
    # ========== 极值话题ID ==========
    max_length_topic_id = Column(BigInteger, nullable=True, comment="最长回声话题ID")
    min_length_topic_id = Column(BigInteger, nullable=True, comment="最短回声话题ID")
    
    # ========== 强度统计 ==========
    intensity_sum = Column(BigInteger, default=0, nullable=False, comment="强度总和")
    intensity_avg = Column(Float, nullable=True, comment="平均强度")
    intensity_max = Column(Integer, nullable=True, comment="最大强度")
    
    # ========== 热度统计 ==========
    heat_sum = Column(Float, nullable=True, comment="热度总和")
    heat_avg = Column(Float, nullable=True, comment="平均热度")
    
    # ========== 索引定义 ==========
    __table_args__ = (
        Index("idx_day_category", "day", "category"),
        UniqueConstraint("day", "category", name="uq_day_category"),
        {"comment": "分类按日聚合指标表"}
    )
    
    def __repr__(self):
        return f"<CategoryDayMetrics(id={self.id}, day={self.day}, category={self.category})>"

