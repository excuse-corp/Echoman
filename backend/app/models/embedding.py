"""
向量嵌入模型

对应文档中的 embeddings 表
存储各对象的向量表示
"""
from sqlalchemy import Column, Integer, String, BigInteger, Index
from pgvector.sqlalchemy import Vector
from .base import Base


class Embedding(Base):
    """向量嵌入"""
    
    __tablename__ = "embeddings"
    
    # ========== 主键 ==========
    id = Column(BigInteger, primary_key=True, autoincrement=True, comment="主键ID")
    
    # ========== 对象类型 ==========
    object_type = Column(
        String(50),
        nullable=False,
        index=True,
        comment="对象类型（source_item|topic_node|topic_summary）"
    )
    object_id = Column(BigInteger, nullable=False, index=True, comment="对象ID")
    
    # ========== 模型信息 ==========
    provider = Column(String(50), nullable=False, comment="提供商（openai|qwen|azure等）")
    model = Column(String(100), nullable=False, comment="模型名称")
    
    # ========== 向量数据 ==========
    vector = Column(Vector(4096), nullable=False, comment="向量数据（Qwen3-Embedding-8B为4096维）")
    
    # ========== 索引定义 ==========
    __table_args__ = (
        Index("idx_object_type_id", "object_type", "object_id"),
        # 注意：pgvector索引最多支持2000维，4096维向量无法创建索引
        # 对于高维向量，需要在应用层进行相似度计算
        {"comment": "向量嵌入表"}
    )
    
    def __repr__(self):
        return f"<Embedding(id={self.id}, object_type={self.object_type}, object_id={self.object_id})>"

