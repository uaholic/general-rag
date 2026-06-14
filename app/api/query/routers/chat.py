"""用户聊天接口。"""
from __future__ import annotations

import asyncio
from typing import Any

from bson import ObjectId
from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse

from app.api.schemas.chat import ChatStreamRequest
from app.infra.persistence.history_repository import history_repository
from app.process.query.agent.main_graph import run_query_graph
from app.shared.utils.sse_utils import SSEEvent, format_sse_event

router = APIRouter(prefix="/api", tags=["chat"])


def _jsonable(value: Any) -> Any:
    if isinstance(value, ObjectId):
        return str(value)
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    if isinstance(value, dict):
        return {key: _jsonable(item) for key, item in value.items()}
    return value


@router.post("/chat/stream")
async def chat_stream(payload: ChatStreamRequest) -> StreamingResponse:
    async def event_generator():
        try:
            history_repository.save_message(
                session_id=payload.session_id,
                role="user",
                content=payload.message,
                company_id=payload.company_id,
                business_line_id=payload.business_line_id,
            )
        except Exception:
            pass

        yield format_sse_event(SSEEvent.READY, {"session_id": payload.session_id})

        try:
            state = run_query_graph(
                session_id=payload.session_id,
                message=payload.message,
                company_id=payload.company_id,
                business_line_id=payload.business_line_id,
            )
        except Exception as exc:
            yield format_sse_event(SSEEvent.ERROR, {"message": str(exc)})
            yield format_sse_event(SSEEvent.FINAL, {"answer": ""})
            return

        rewritten_query = state.get("rewritten_query", "")
        if rewritten_query and rewritten_query != payload.message:
            yield format_sse_event(SSEEvent.REWRITE, {"rewritten_query": rewritten_query})

        for progress in state.get("progress", []):
            yield format_sse_event(SSEEvent.PROGRESS, progress)
            await asyncio.sleep(0.02)

        answer = state.get("answer", "")
        for char in answer:
            yield format_sse_event(SSEEvent.DELTA, {"text": char})
            await asyncio.sleep(0.005)

        images = state.get("images", [])
        if images:
            yield format_sse_event(SSEEvent.IMAGE, {"placement": "inline", "images": images})

        references = state.get("references", [])
        yield format_sse_event(SSEEvent.REFERENCES, {"references": references})
        yield format_sse_event(SSEEvent.FINAL, {"answer": answer})

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@router.get("/chat/history")
async def chat_history(
    session_id: str = Query(...),
    business_line_id: str = Query(...),
):
    try:
        messages = _jsonable(history_repository.list_recent(session_id=session_id, limit=100))
    except Exception:
        messages = []
    return {"session_id": session_id, "business_line_id": business_line_id, "messages": messages}
