"""企业配置 schema。"""
from __future__ import annotations

from pydantic import BaseModel


class CompanySaveRequest(BaseModel):
    company_name: str
    industry: str = ""
    company_description: str = ""
    business_scope: str = ""
    answer_tone: str = ""
    welcome_message: str = ""
    fallback_message: str = ""
    disclaimer: str = ""
