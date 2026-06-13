"""登录 schema。"""
from __future__ import annotations

from pydantic import BaseModel


class LoginRequest(BaseModel):
    secret: str = ""
