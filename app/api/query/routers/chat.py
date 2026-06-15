"""用户聊天接口。"""
from __future__ import annotations

import asyncio
from typing import Any

from bson import ObjectId
from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse

from app.api.schemas.chat import ChatStreamRequest
from app.infra.persistence.history_repository import history_repository
from app.process.common import progress_event
from app.rag.query import (
    answer_generation_service,
    query_history_service,
    query_retrieval_service,
    query_runtime_service,
)
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
        user_message_id = ""
        try:
            user_message_id = history_repository.save_message(
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
            runtime = query_runtime_service.load_runtime(payload.business_line_id)
            yield format_sse_event(
                SSEEvent.PROGRESS,
                progress_event(step="load_config", label="读取业务线配置", current=1, total=7),
            )

            kb_ids = runtime.get("kb_ids", [])
            yield format_sse_event(
                SSEEvent.PROGRESS,
                progress_event(
                    step="load_kb",
                    label="读取绑定知识库",
                    current=2,
                    total=7,
                    message="当前业务线没有绑定可用知识库" if not kb_ids else "已读取当前业务线绑定知识库",
                ),
            )

            model_config = runtime.get("model_config") or {}
            business_line = runtime.get("business_line") or {}
            rewritten = query_retrieval_service.rewrite_query(
                question=payload.message,
                session_id=payload.session_id,
                business_line=business_line,
                model_name=model_config.get("llm_model_name", ""),
            )
            rewritten_query = rewritten.get("rewritten_query") or payload.message
            query_subject_names = rewritten.get("query_subject_names") or []
            yield format_sse_event(SSEEvent.REWRITE, {"rewritten_query": rewritten_query})
            yield format_sse_event(
                SSEEvent.PROGRESS,
                progress_event(step="rewrite", label="改写问题", current=3, total=7, message="已结合历史改写问题"),
            )

            chunks = query_retrieval_service.search(
                query=rewritten_query,
                kb_ids=kb_ids,
                top_k=runtime.get("top_k", 5),
                use_milvus=True,
            )
            yield format_sse_event(
                SSEEvent.PROGRESS,
                progress_event(
                    step="retrieve",
                    label="检索相关资料",
                    current=4,
                    total=7,
                    message=f"检索到 {len(chunks)} 条候选片段",
                ),
            )

            reranked_chunks = query_retrieval_service.rerank(
                query=rewritten_query,
                chunks=chunks,
                top_k=runtime.get("top_k", 5),
                use_rerank=runtime.get("use_rerank", False),
            )
            references = query_retrieval_service.build_references(reranked_chunks)
            images = query_retrieval_service.collect_images(reranked_chunks)
            yield format_sse_event(
                SSEEvent.PROGRESS,
                progress_event(
                    step="rerank",
                    label="整理引用来源",
                    current=5,
                    total=7,
                    message=f"整理出 {len(references)} 条引用",
                ),
            )

            yield format_sse_event(
                SSEEvent.PROGRESS,
                progress_event(step="generate", label="生成回答", current=6, total=7, message="大模型正在生成回答"),
            )

            answer_parts: list[str] = []
            for text in answer_generation_service.stream_generate(
                question=payload.message,
                business_line=business_line,
                chunks=reranked_chunks,
                model_name=model_config.get("llm_model_name", ""),
                use_llm=True,
            ):
                answer_parts.append(text)
                yield format_sse_event(SSEEvent.DELTA, {"text": text})
                await asyncio.sleep(0)
            answer = "".join(answer_parts)

            state = {
                "session_id": payload.session_id,
                "company_id": payload.company_id,
                "business_line_id": payload.business_line_id,
                "user_message_id": user_message_id,
                "question": payload.message,
                "rewritten_query": rewritten_query,
                "query_subject_names": query_subject_names,
                "business_line": business_line,
                "model_config": model_config,
                "reranked_chunks": reranked_chunks,
                "references": references,
                "images": images,
                "answer": answer,
            }
            query_history_service.update_user_message(state)
            query_history_service.save_assistant_message(state)
            yield format_sse_event(
                SSEEvent.PROGRESS,
                progress_event(step="save_history", label="保存聊天记录", current=7, total=7, message="完成"),
            )
        except Exception as exc:
            yield format_sse_event(SSEEvent.ERROR, {"message": str(exc)})
            yield format_sse_event(SSEEvent.FINAL, {"answer": ""})
            return

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
