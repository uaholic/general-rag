"""登录相关接口。"""
from __future__ import annotations

from fastapi import APIRouter

from app.api.schemas.auth import LoginRequest
from app.api.schemas.common import ApiResponse

router = APIRouter(tags=["auth"])


@router.post("/login", response_model=ApiResponse)
async def login(payload: LoginRequest) -> ApiResponse:
    return ApiResponse(message="开发模式已允许访问后台", data={"authenticated": True, "secret_present": bool(payload.secret)})


@router.post("/logout", response_model=ApiResponse)
async def logout() -> ApiResponse:
    return ApiResponse(message="已退出开发模式会话", data={"authenticated": False})
