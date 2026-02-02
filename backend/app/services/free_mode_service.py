"""
自由模式邀请码与访问令牌服务
"""
import secrets
from datetime import timedelta
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models import FreeModeInvite, FreeModeAccessToken
from app.utils.timezone import now_cn


class FreeModeService:
    """自由模式邀请码验证与访问令牌管理"""

    def __init__(self, token_ttl_hours: Optional[int] = None):
        self.token_ttl_hours = token_ttl_hours or settings.free_mode_token_ttl_hours

    async def verify_invite_code(self, db: AsyncSession, code: str) -> FreeModeAccessToken:
        """验证邀请码并签发访问令牌"""
        normalized = code.strip()
        if not normalized:
            raise ValueError("邀请码不能为空")

        stmt = select(FreeModeInvite).where(FreeModeInvite.code == normalized)
        result = await db.execute(stmt)
        invite = result.scalar_one_or_none()
        if not invite:
            raise ValueError("邀请码无效或已过期")
        if not invite.is_active():
            raise ValueError("邀请码无效或已过期")

        # 如果未设置过期时间，默认按创建时间 + TTL 天数处理
        if invite.expires_at is None and invite.created_at:
            ttl_days = settings.free_mode_invite_ttl_days
            if ttl_days > 0 and invite.created_at + timedelta(days=ttl_days) < now_cn():
                raise ValueError("邀请码已过期")

        token = self._generate_token()
        expires_at = now_cn() + timedelta(hours=self.token_ttl_hours) if self.token_ttl_hours else None

        access_token = FreeModeAccessToken(
            invite_id=invite.id,
            token=token,
            expires_at=expires_at,
            last_used_at=now_cn(),
        )

        invite.used_count = (invite.used_count or 0) + 1
        invite.last_used_at = now_cn()

        db.add(access_token)
        db.add(invite)
        await db.commit()
        await db.refresh(access_token)
        return access_token

    async def validate_access_token(self, db: AsyncSession, token: str) -> FreeModeAccessToken:
        """校验访问令牌"""
        normalized = (token or "").strip()
        if not normalized:
            raise ValueError("缺少自由模式访问令牌")

        stmt = select(FreeModeAccessToken).where(FreeModeAccessToken.token == normalized)
        result = await db.execute(stmt)
        access_token = result.scalar_one_or_none()
        if not access_token or access_token.revoked:
            raise ValueError("访问令牌无效")

        if access_token.expires_at and access_token.expires_at < now_cn():
            raise ValueError("访问令牌已过期")

        access_token.last_used_at = now_cn()
        db.add(access_token)
        await db.commit()
        return access_token

    def _generate_token(self) -> str:
        return secrets.token_urlsafe(32)
