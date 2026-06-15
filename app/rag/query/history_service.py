"""查询历史保存服务。"""
from __future__ import annotations

from typing import Any

from app.infra.persistence.history_repository import history_repository


class QueryHistoryService:
    """隔离 MongoDB 聊天历史写入，避免节点里到处 try/except。"""

    def update_user_message(self, state: dict[str, Any]) -> None:
        message_id = state.get("user_message_id")
        if not message_id:
            return
        try:
            history_repository.save_message(
                session_id=state["session_id"],
                role="user",
                content=state.get("question", ""),
                rewritten_query=state.get("rewritten_query", ""),
                subject_names=state.get("query_subject_names", []),
                company_id=state.get("company_id", "default_company"),
                business_line_id=state.get("business_line_id", ""),
                message_id=message_id,
            )
        except Exception:
            return

    def save_assistant_message(self, state: dict[str, Any]) -> None:
        try:
            subject_names = []
            for chunk in state.get("reranked_chunks", []):
                for name in chunk.get("subject_names", []) or []:
                    if name not in subject_names:
                        subject_names.append(name)
            if not subject_names:
                subject_names = state.get("query_subject_names", [])
            history_repository.save_message(
                session_id=state["session_id"],
                role="assistant",
                content=state.get("answer", ""),
                rewritten_query=state.get("rewritten_query", ""),
                subject_names=subject_names,
                references=state.get("references", []),
                image_urls=[image.get("url", "") for image in state.get("images", [])],
                company_id=state.get("company_id", "default_company"),
                business_line_id=state.get("business_line_id", ""),
            )
        except Exception:
            # MongoDB 不可用不能影响用户问答。
            return


query_history_service = QueryHistoryService()
