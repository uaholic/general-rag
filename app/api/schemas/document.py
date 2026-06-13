"""文档 schema。"""
from __future__ import annotations

from pydantic import BaseModel


class DocumentUploadResponse(BaseModel):
    success: bool = True
    doc_id: str
    task_id: str
    message: str = "已提交解析"
