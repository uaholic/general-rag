"""知识库管理接口。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.api.deps import get_db_session
from app.api.frontend import admin_page_response
from app.api.schemas.common import ApiResponse
from app.api.schemas.knowledge_base import (
    KnowledgeBaseCreateRequest,
    KnowledgeBaseToggleRequest,
    KnowledgeBaseUpdateRequest,
)
from app.infra.persistence.admin_repositories import KnowledgeBaseRepository

router = APIRouter(prefix="/admin/kb", tags=["knowledge-base"])


@router.get("", include_in_schema=False)
async def knowledge_base_page() -> FileResponse:
    return admin_page_response()


@router.get("/list")
async def list_knowledge_bases(session: Session = Depends(get_db_session)):
    return {"items": KnowledgeBaseRepository(session).list_with_business_lines()}


@router.post("/create", response_model=ApiResponse)
async def create_knowledge_base(
    payload: KnowledgeBaseCreateRequest,
    session: Session = Depends(get_db_session),
) -> ApiResponse:
    repo = KnowledgeBaseRepository(session)
    kb = repo.save(payload.model_dump())
    session.commit()
    return ApiResponse(message="知识库已保存", data=repo.to_dict(kb, repo.bound_business_lines(kb.kb_id)))


@router.post("/{kb_id}/update", response_model=ApiResponse)
async def update_knowledge_base(
    kb_id: str,
    payload: KnowledgeBaseUpdateRequest,
    session: Session = Depends(get_db_session),
) -> ApiResponse:
    repo = KnowledgeBaseRepository(session)
    bound_before = repo.bound_business_lines(kb_id) if not payload.enabled else []
    kb = repo.save(payload.model_dump(), kb_id=kb_id)
    session.commit()
    data = repo.to_dict(kb, repo.bound_business_lines(kb.kb_id))
    data["unbound_business_lines"] = [
        {"business_line_id": line.id, "business_line_name": line.business_line_name}
        for line in bound_before
    ]
    message = "知识库已保存"
    if bound_before:
        message = f"知识库已停用，已自动取消 {len(bound_before)} 个业务线绑定"
    return ApiResponse(message=message, data=data)


@router.post("/{kb_id}/toggle", response_model=ApiResponse)
async def toggle_knowledge_base(
    kb_id: str,
    payload: KnowledgeBaseToggleRequest,
    session: Session = Depends(get_db_session),
) -> ApiResponse:
    repo = KnowledgeBaseRepository(session)
    bound_before = repo.bound_business_lines(kb_id) if not payload.enabled else []
    kb = repo.toggle(kb_id, payload.enabled)
    if kb is None:
        raise HTTPException(status_code=404, detail="知识库不存在")
    session.commit()
    data = repo.to_dict(kb, repo.bound_business_lines(kb.kb_id))
    data["unbound_business_lines"] = [
        {"business_line_id": line.id, "business_line_name": line.business_line_name}
        for line in bound_before
    ]
    message = "知识库状态已更新"
    if bound_before:
        message = f"知识库已停用，已自动取消 {len(bound_before)} 个业务线绑定"
    return ApiResponse(message=message, data=data)


@router.post("/{kb_id}/delete", response_model=ApiResponse)
async def delete_knowledge_base(kb_id: str, session: Session = Depends(get_db_session)) -> ApiResponse:
    deleted = KnowledgeBaseRepository(session).delete(kb_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="知识库不存在")
    session.commit()
    return ApiResponse(message="知识库已删除", data={"kb_id": kb_id})
