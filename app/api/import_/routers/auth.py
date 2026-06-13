"""登录相关接口。

第一版暂不做真实登录，只保留接口位置，避免后续路由结构再变。
"""
from __future__ import annotations

from fastapi import APIRouter

from app.api.schemas.auth import LoginRequest
from app.api.schemas.common import ApiResponse

router = APIRouter(tags=["auth"])


@router.post("/login", response_model=ApiResponse)
async def login(payload: LoginRequest) -> ApiResponse:
    # TODO: 暂时不做登录鉴权；后续如需要再接 session/cookie。
    return ApiResponse(message="登录功能暂未启用，当前默认允许访问后台", data=payload.model_dump())


@router.post("/logout", response_model=ApiResponse)
async def logout() -> ApiResponse:
    # TODO: 暂时不做登录态清理。
    return ApiResponse(message="退出功能暂未启用")
