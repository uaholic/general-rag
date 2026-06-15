"""用户查询图 State。"""
from __future__ import annotations

from typing import Any, TypedDict


class QueryGraphState(TypedDict, total=False):
    session_id: str
    company_id: str
    business_line_id: str
    question: str
    user_message_id: str

    company_config: dict[str, Any]
    model_config: dict[str, Any]
    business_line: dict[str, Any]
    kb_ids: list[str]

    rewritten_query: str
    query_subject_names: list[str]
    retrieved_chunks: list[dict[str, Any]]
    reranked_chunks: list[dict[str, Any]]
    references: list[dict[str, Any]]
    images: list[dict[str, Any]]
    answer: str

    use_milvus: bool
    use_rerank: bool
    use_llm: bool
    top_k: int
    error_msg: str
    progress: list[dict[str, Any]]
