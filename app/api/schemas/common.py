"""通用响应模型。"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ApiResponse(BaseModel):
    success: bool = True
    message: str = "success"
    data: Any | None = None


class PageResult(BaseModel):
    items: list[Any] = Field(default_factory=list)
    total: int = 0
