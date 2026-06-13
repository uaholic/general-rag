"""后台问答测试 schema。"""
from __future__ import annotations

from pydantic import BaseModel, Field


class PlaygroundChatRequest(BaseModel):
    business_line_id: str = Field(..., min_length=1)
    message: str = Field(..., min_length=1)
