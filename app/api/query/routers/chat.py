"""用户聊天接口。"""
from __future__ import annotations

import asyncio
from typing import Any

from bson import ObjectId
from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse

from app.api.schemas.chat import ChatStreamRequest
from app.infra.persistence.history_repository import history_repository
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
    # TODO: 调用 QueryGraph，并把图节点回调转换成 SSE。
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
        steps = [
            ("load_config", "读取业务线配置"),
            ("load_kb", "读取绑定知识库"),
            ("retrieve", "检索相关资料"),
            ("generate", "生成回答"),
        ]
        for index, (step, label) in enumerate(steps, start=1):
            yield format_sse_event(
                SSEEvent.PROGRESS,
                {
                    "step": step,
                    "label": label,
                    "current": index,
                    "total": len(steps),
                    "percent": round(index / len(steps) * 100),
                    "message": label,
                },
            )
            await asyncio.sleep(0.05)

        answer = "这是一个后端框架占位回答。后续这里会接 QueryGraph、Milvus 检索、Rerank 和 LLM 流式生成。"
        for char in answer:
            yield format_sse_event(SSEEvent.DELTA, {"text": char})
            await asyncio.sleep(0.005)

        yield format_sse_event(
            SSEEvent.IMAGE,
            {
                "placement": "inline",
                "message": "后续如果检索结果包含图片，可以在这里展示。",
                "images": [],
            },
        )
        references = []
        yield format_sse_event(SSEEvent.REFERENCES, {"references": references})
        yield format_sse_event(SSEEvent.FINAL, {"answer": answer})
        try:
            history_repository.save_message(
                session_id=payload.session_id,
                role="assistant",
                content=answer,
                references=references,
                company_id=payload.company_id,
                business_line_id=payload.business_line_id,
            )
        except Exception:
            pass

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
