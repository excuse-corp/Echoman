"""
运行记录模型

对应文档中的 runs_ingest、runs_pipeline 表
用于追踪采集和流水线执行情况
"""
from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, DateTime, Float, Index
from sqlalchemy.dialects.postgresql import JSONB
from .base import Base
from app.utils.timezone import now_cn


class RunIngest(Base):
    """采集运行记录"""
    
    __tablename__ = "runs_ingest"
    
    # ========== 主键 ==========
    run_id = Column(String(50), primary_key=True, comment="运行ID")
    
    # ========== 状态 ==========
    status = Column(
        String(20),
        default="running",
        nullable=False,
        index=True,
        comment="状态（running|success|failed|partial）"
    )
    
    # ========== 时间字段 ==========
    started_at = Column(DateTime, default=now_cn, nullable=False, comment="开始时间")
    ended_at = Column(DateTime, nullable=True, comment="结束时间")
    duration_ms = Column(Integer, nullable=True, comment="持续时间（毫秒）")
    
    # ========== 统计信息 ==========
    total_platforms = Column(Integer, default=0, nullable=False, comment="总平台数")
    success_platforms = Column(Integer, default=0, nullable=False, comment="成功平台数")
    failed_platforms = Column(Integer, default=0, nullable=False, comment="失败平台数")
    total_items = Column(Integer, default=0, nullable=False, comment="总抓取条数")
    success_items = Column(Integer, default=0, nullable=False, comment="成功解析条数")
    failed_items = Column(Integer, default=0, nullable=False, comment="失败解析条数")
    
    # ========== 详细结果 ==========
    platform_results = Column(JSONB, nullable=True, comment="各平台结果详情（JSON）")
    error_summary = Column(Text, nullable=True, comment="错误汇总")
    
    # ========== 配置信息 ==========
    config = Column(JSONB, nullable=True, comment="运行配置（JSON）")
    
    # ========== 计算属性 ==========
    @property
    def parse_success_rate(self) -> float:
        """解析成功率"""
        if self.total_items == 0:
            return 0.0
        return round(self.success_items / self.total_items, 4)
    
    # ========== 索引定义 ==========
    __table_args__ = (
        Index("idx_status_started", "status", "started_at"),
        {"comment": "采集运行记录表"}
    )
    
    def __repr__(self):
        return f"<RunIngest(run_id={self.run_id}, status={self.status})>"


class RunPipeline(Base):
    """流水线运行记录"""
    
    __tablename__ = "runs_pipeline"
    
    # ========== 主键 ==========
    run_id = Column(String(50), primary_key=True, comment="运行ID")
    
    # ========== 阶段信息 ==========
    stage = Column(
        String(50),
        nullable=False,
        index=True,
        comment="阶段（halfday_merge|global_merge|classify|summarize等）"
    )
    
    # ========== 状态 ==========
    status = Column(
        String(20),
        default="running",
        nullable=False,
        index=True,
        comment="状态（running|success|failed|partial）"
    )
    
    # ========== 时间字段 ==========
    started_at = Column(DateTime, default=now_cn, nullable=False, comment="开始时间")
    ended_at = Column(DateTime, nullable=True, comment="结束时间")
    duration_ms = Column(Integer, nullable=True, comment="持续时间（毫秒）")
    
    # ========== 统计信息 ==========
    input_count = Column(Integer, default=0, nullable=False, comment="输入数量")
    output_count = Column(Integer, default=0, nullable=False, comment="输出数量")
    success_count = Column(Integer, default=0, nullable=False, comment="成功数量")
    failed_count = Column(Integer, default=0, nullable=False, comment="失败数量")
    
    # ========== 详细结果 ==========
    results = Column(JSONB, nullable=True, comment="结果详情（JSON）")
    error_summary = Column(Text, nullable=True, comment="错误汇总")
    
    # ========== 性能指标 ==========
    metrics = Column(JSONB, nullable=True, comment="性能指标（JSON）")
    
    # ========== 索引定义 ==========
    __table_args__ = (
        Index("idx_stage_status", "stage", "status"),
        Index("idx_started_at", "started_at"),
        {"comment": "流水线运行记录表"}
    )
    
    def __repr__(self):
        return f"<RunPipeline(run_id={self.run_id}, stage={self.stage}, status={self.status})>"

