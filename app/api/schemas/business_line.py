"""业务线配置 schema。"""
from __future__ import annotations

from pydantic import BaseModel, Field


class BusinessLineSaveRequest(BaseModel):
    business_line_id: str | None = None
    business_line_name: str = Field(..., min_length=1)
    business_line_description: str = ""
    scenario: str = ""
    target_user: str = ""
    assistant_role: str = ""
    welcome_message: str = ""
    fallback_message: str = ""
    prompt_extra: str = ""
    kb_ids: list[str] = Field(default_factory=list)
    enabled: bool = True


class ToggleRequest(BaseModel):
    enabled: bool
