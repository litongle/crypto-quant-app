"""用户 API"""
from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.deps import CurrentUser
from app.models.user import User

router = APIRouter()


@router.get("/me")
async def get_current_user_info(
    current_user: CurrentUser,
) -> dict:
    """获取当前用户信息（需认证）"""
    return {
        "id": current_user.id,
        "email": current_user.email,
        "name": current_user.name,
        "risk_level": current_user.risk_level,
        "status": current_user.status,
    }
