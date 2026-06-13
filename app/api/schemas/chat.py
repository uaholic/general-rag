"""聊天 schema。"""
from __future__ import annotations

from pydantic import BaseModel, Field


class WidgetConfigResponse(BaseModel):
    company_name: str
    business_line_id: str
    business_line_name: str
    welcome_message: str
    fallback_message: str
    bound_kb_ids: list[str] = Field(default_factory=list)
    theme_color: str


class ChatStreamRequest(BaseModel):
    session_id: str = Field(..., min_length=1)
    message: str = Field(..., min_length=1)
    company_id: str = "default_company"
    business_line_id: str = Field(..., min_length=1)
