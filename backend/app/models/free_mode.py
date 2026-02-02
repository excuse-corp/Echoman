"""
自由模式邀请码与访问令牌
"""
from sqlalchemy import Column, String, Integer, DateTime, BigInteger, Boolean, Text, ForeignKey, Index
from sqlalchemy.orm import relationship
from .base import Base
from app.utils.timezone import now_cn


class FreeModeInvite(Base):
    """自由模式邀请码"""

    __tablename__ = "free_mode_invites"

    id = Column(BigInteger, primary_key=True, autoincrement=True, comment="主键ID")
    code = Column(String(64), nullable=False, unique=True, index=True, comment="邀请码")
    status = Column(String(20), default="active", nullable=False, index=True, comment="状态（active|disabled）")
    max_uses = Column(Integer, nullable=True, comment="最大可使用次数（null表示不限）")
    used_count = Column(Integer, default=0, nullable=False, comment="已使用次数")
    expires_at = Column(DateTime, nullable=True, comment="过期时间")
    last_used_at = Column(DateTime, nullable=True, comment="最近使用时间")
    note = Column(Text, nullable=True, comment="备注")

    tokens = relationship("FreeModeAccessToken", back_populates="invite", cascade="all, delete-orphan")

    __table_args__ = (
        Index("idx_free_mode_invite_status_expires", "status", "expires_at"),
        {"comment": "自由模式邀请码"},
    )

    def is_active(self) -> bool:
        if self.status != "active":
            return False
        if self.expires_at and self.expires_at < now_cn():
            return False
        if self.max_uses is not None and self.used_count >= self.max_uses:
            return False
        return True


class FreeModeAccessToken(Base):
    """自由模式访问令牌"""

    __tablename__ = "free_mode_access_tokens"

    id = Column(BigInteger, primary_key=True, autoincrement=True, comment="主键ID")
    invite_id = Column(
        BigInteger,
        ForeignKey("free_mode_invites.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="邀请码ID",
    )
    token = Column(String(128), nullable=False, unique=True, index=True, comment="访问令牌")
    expires_at = Column(DateTime, nullable=True, comment="过期时间")
    last_used_at = Column(DateTime, nullable=True, comment="最近使用时间")
    revoked = Column(Boolean, default=False, nullable=False, comment="是否吊销")

    invite = relationship("FreeModeInvite", back_populates="tokens")

    __table_args__ = (
        Index("idx_free_mode_token_expires", "expires_at"),
        {"comment": "自由模式访问令牌"},
    )
