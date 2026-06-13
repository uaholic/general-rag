"""后台问答测试接口。"""
from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import FileResponse

from app.api.frontend import admin_page_response
from app.api.schemas.playground import PlaygroundChatRequest

router = APIRouter(prefix="/admin/playground", tags=["playground"])


@router.get("", include_in_schema=False)
async def playground_page() -> FileResponse:
    return admin_page_response()


@router.post("/chat")
async def playground_chat(payload: PlaygroundChatRequest):
    # TODO: 调用 QueryGraph，source=playground，可先非流式返回。
    return {
        "answer": "后台测试回答接口待实现。",
        "references": [],
        "debug": payload.model_dump(),
    }
