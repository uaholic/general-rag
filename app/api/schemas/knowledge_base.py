"""知识库 schema。"""
from __future__ import annotations

from pydantic import BaseModel, Field


class KnowledgeBaseCreateRequest(BaseModel):
    kb_id: str | None = None
    name: str = Field(..., min_length=1)
    description: str = ""
    enabled: bool = True


class KnowledgeBaseUpdateRequest(KnowledgeBaseCreateRequest):
    pass


class KnowledgeBaseToggleRequest(BaseModel):
    enabled: bool
