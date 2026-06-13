"""模型配置 schema。"""
from __future__ import annotations

from pydantic import BaseModel


class ModelConfigSaveRequest(BaseModel):
    llm_model_name: str = ""
    embedding_model_name: str = ""
    rerank_model_name: str = ""
    image_model_name: str = ""
    top_k: int = 5
    use_rerank: bool = False
