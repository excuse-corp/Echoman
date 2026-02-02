"""
自由模式相关API
"""
from typing import Optional
from pydantic import BaseModel
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import get_db
from app.services.free_mode_service import FreeModeService

router = APIRouter()


class InviteVerifyRequest(BaseModel):
    code: str


class InviteVerifyResponse(BaseModel):
    valid: bool
    token: Optional[str] = None
    expires_at: Optional[str] = None


@router.post("/verify", response_model=InviteVerifyResponse)
async def verify_invite_code(
    request: InviteVerifyRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    校验邀请码并签发访问令牌
    """
    service = FreeModeService()
    try:
        access_token = await service.verify_invite_code(db, request.code)
        return InviteVerifyResponse(
            valid=True,
            token=access_token.token,
            expires_at=access_token.expires_at.isoformat() if access_token.expires_at else None
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"邀请码校验失败: {str(e)}")
