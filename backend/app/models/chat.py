"""
对话相关模型

对应文档中的 chats、chat_messages、citations 表
"""
from datetime import datetime
from app.utils.timezone import now_cn
from sqlalchemy import Column, Integer, String, Text, DateTime, BigInteger, ForeignKey, Index
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
from .base import Base


class Chat(Base):
    """会话"""
    
    __tablename__ = "chats"
    
    # ========== 主键 ==========
    id = Column(BigInteger, primary_key=True, autoincrement=True, comment="主键ID")
    
    # ========== 会话信息 ==========
    title = Column(String(200), nullable=True, comment="会话标题（可选）")
    mode = Column(
        String(20),
        default="global",
        nullable=False,
        comment="对话模式（topic|global）"
    )
    
    # ========== 关联主题 ==========
    topic_id = Column(BigInteger, nullable=True, index=True, comment="关联主题ID（topic模式时使用）")
    
    # ========== 状态 ==========
    is_active = Column(Integer, default=1, nullable=False, comment="是否活跃")
    
    # ========== 关系定义 ==========
    messages = relationship("ChatMessage", back_populates="chat", cascade="all, delete-orphan")
    
    # ========== 索引定义 ==========
    __table_args__ = (
        Index("idx_topic_created", "topic_id", "created_at"),
        {"comment": "会话表"}
    )
    
    def __repr__(self):
        return f"<Chat(id={self.id}, mode={self.mode})>"


class ChatMessage(Base):
    """对话消息"""
    
    __tablename__ = "chat_messages"
    
    # ========== 主键 ==========
    id = Column(BigInteger, primary_key=True, autoincrement=True, comment="主键ID")
    
    # ========== 外键关联 ==========
    chat_id = Column(
        BigInteger,
        ForeignKey("chats.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="会话ID"
    )
    
    # ========== 消息内容 ==========
    role = Column(String(20), nullable=False, comment="角色（user|assistant|system）")
    content = Column(Text, nullable=False, comment="消息内容")
    
    # ========== 回答元数据 ==========
    answer_meta = Column(JSONB, nullable=True, comment="回答元数据（latency/tokens/provider等）")
    
    # ========== 时间戳 ==========
    sent_at = Column(DateTime, default=now_cn, nullable=False, comment="发送时间")
    
    # ========== 关系定义 ==========
    chat = relationship("Chat", back_populates="messages")
    citations = relationship("Citation", back_populates="message", cascade="all, delete-orphan")
    
    # ========== 索引定义 ==========
    __table_args__ = (
        Index("idx_chat_sent", "chat_id", "sent_at"),
        {"comment": "对话消息表"}
    )
    
    def __repr__(self):
        return f"<ChatMessage(id={self.id}, chat_id={self.chat_id}, role={self.role})>"


class Citation(Base):
    """引用"""
    
    __tablename__ = "citations"
    
    # ========== 主键 ==========
    id = Column(BigInteger, primary_key=True, autoincrement=True, comment="主键ID")
    
    # ========== 外键关联 ==========
    message_id = Column(
        BigInteger,
        ForeignKey("chat_messages.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="消息ID"
    )
    
    # ========== 引用信息 ==========
    topic_id = Column(BigInteger, nullable=True, comment="主题ID")
    node_id = Column(BigInteger, nullable=True, comment="节点ID")
    source_url = Column(String(1000), nullable=True, comment="源链接")
    snippet = Column(Text, nullable=True, comment="引用片段")
    
    # ========== 关系定义 ==========
    message = relationship("ChatMessage", back_populates="citations")
    
    # ========== 索引定义 ==========
    __table_args__ = (
        Index("idx_message_topic", "message_id", "topic_id"),
        {"comment": "引用表"}
    )
    
    def __repr__(self):
        return f"<Citation(id={self.id}, message_id={self.message_id}, topic_id={self.topic_id})>"

