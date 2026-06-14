"""查询历史保存服务。"""
from __future__ import annotations

from typing import Any

from app.infra.persistence.history_repository import history_repository


class QueryHistoryService:
    """隔离 MongoDB 聊天历史写入，避免节点里到处 try/except。"""

    def save_assistant_message(self, state: dict[str, Any]) -> None:
        try:
            history_repository.save_message(
                session_id=state["session_id"],
                role="assistant",
                content=state.get("answer", ""),
                references=state.get("references", []),
                image_urls=[image.get("url", "") for image in state.get("images", [])],
                company_id=state.get("company_id", "default_company"),
                business_line_id=state.get("business_line_id", ""),
            )
        except Exception:
            # MongoDB 不可用不能影响用户问答。
            return


query_history_service = QueryHistoryService()
