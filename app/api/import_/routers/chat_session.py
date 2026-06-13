"""聊天记录管理接口。"""
from __future__ import annotations

from typing import Any

from bson import ObjectId
from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.api.deps import get_db_session
from app.api.frontend import admin_page_response
from app.api.schemas.common import ApiResponse
from app.infra.persistence.admin_repositories import BusinessLineRepository
from app.shared.clients.mongo_history_utils import (
    clear_all_history,
    clear_history,
    get_recent_messages,
    list_chat_sessions,
)

router = APIRouter(prefix="/admin/chat-sessions", tags=["chat-session"])


@router.get("", include_in_schema=False)
async def chat_session_page() -> FileResponse:
    return admin_page_response()


def _jsonable(value: Any) -> Any:
    if isinstance(value, ObjectId):
        return str(value)
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    if isinstance(value, dict):
        return {key: _jsonable(item) for key, item in value.items()}
    return value


@router.get("/list")
async def list_sessions(session: Session = Depends(get_db_session)):
    try:
        lines = {
            item["business_line_id"]: item["business_line_name"]
            for item in BusinessLineRepository(session).list_with_kbs()
        }
        items = []
        for item in list_chat_sessions(limit=100):
            normalized = _jsonable(item)
            business_line_id = normalized.get("business_line_id", "")
            normalized["business_line_name"] = lines.get(business_line_id, business_line_id)
            items.append(normalized)
        return {"items": items, "available": True}
    except Exception as exc:
        return {"items": [], "available": False, "message": f"MongoDB 聊天记录暂不可用：{exc}"}


@router.get("/{session_id}")
async def get_chat_session(session_id: str):
    try:
        return {
            "session_id": session_id,
            "messages": _jsonable(get_recent_messages(session_id, limit=100)),
            "available": True,
        }
    except Exception as exc:
        return {"session_id": session_id, "messages": [], "available": False, "message": f"MongoDB 聊天记录暂不可用：{exc}"}


@router.post("/{session_id}/clear", response_model=ApiResponse)
async def clear_chat_session(session_id: str) -> ApiResponse:
    try:
        count = clear_history(session_id)
        return ApiResponse(message="会话已清空", data={"session_id": session_id, "deleted_count": count})
    except Exception as exc:
        return ApiResponse(success=False, message=f"MongoDB 聊天记录暂不可用：{exc}", data={"session_id": session_id})


@router.post("/clear-all", response_model=ApiResponse)
async def clear_all_chat_sessions() -> ApiResponse:
    try:
        count = clear_all_history()
        return ApiResponse(message="全部会话已清空", data={"deleted_count": count})
    except Exception as exc:
        return ApiResponse(success=False, message=f"MongoDB 聊天记录暂不可用：{exc}")
