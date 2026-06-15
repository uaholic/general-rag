"""后台问答测试接口。"""
from __future__ import annotations

from uuid import uuid4

from fastapi import APIRouter
from fastapi.responses import FileResponse

from app.api.frontend import admin_page_response
from app.api.schemas.playground import PlaygroundChatRequest
from app.process.query.agent.main_graph import run_query_graph

router = APIRouter(prefix="/admin/playground", tags=["playground"])


@router.get("", include_in_schema=False)
async def playground_page() -> FileResponse:
    return admin_page_response()


@router.post("/chat")
async def playground_chat(payload: PlaygroundChatRequest):
    session_id = f"playground_{uuid4().hex[:12]}"
    state = run_query_graph(
        session_id=session_id,
        message=payload.message,
        business_line_id=payload.business_line_id,
        use_llm=True,
    )
    return {
        "answer": state.get("answer", ""),
        "references": state.get("references", []),
        "images": state.get("images", []),
        "progress": state.get("progress", []),
        "debug": {
            "session_id": session_id,
            "rewritten_query": state.get("rewritten_query", ""),
            "retrieved_count": len(state.get("retrieved_chunks", [])),
        },
    }
