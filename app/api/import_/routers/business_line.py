"""业务线配置接口。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.api.deps import get_db_session
from app.api.frontend import admin_page_response
from app.api.schemas.business_line import BusinessLineSaveRequest, ToggleRequest
from app.api.schemas.common import ApiResponse
from app.infra.persistence.admin_repositories import BusinessLineRepository, KnowledgeBaseRepository

router = APIRouter(prefix="/admin/business-line", tags=["business-line"])


@router.get("", include_in_schema=False)
async def business_line_page() -> FileResponse:
    return admin_page_response()


@router.get("/list")
async def list_business_lines(session: Session = Depends(get_db_session)):
    return {"items": BusinessLineRepository(session).list_with_kbs()}


@router.post("/save", response_model=ApiResponse)
async def save_business_line(payload: BusinessLineSaveRequest, session: Session = Depends(get_db_session)) -> ApiResponse:
    if not payload.kb_ids:
        raise HTTPException(status_code=400, detail="业务线至少需要绑定一个知识库")
    invalid_kbs = KnowledgeBaseRepository(session).disabled_or_missing(payload.kb_ids)
    if invalid_kbs:
        labels = "、".join(f"{item['name']}（{item['reason']}）" for item in invalid_kbs)
        raise HTTPException(status_code=400, detail=f"不能绑定不存在或已停用的知识库：{labels}")
    repo = BusinessLineRepository(session)
    line = repo.save(payload.model_dump())
    session.commit()
    return ApiResponse(message="业务线已保存", data=repo.to_dict(line))


@router.post("/{business_line_id}/toggle", response_model=ApiResponse)
async def toggle_business_line(
    business_line_id: str,
    payload: ToggleRequest,
    session: Session = Depends(get_db_session),
) -> ApiResponse:
    repo = BusinessLineRepository(session)
    line = repo.toggle(business_line_id, payload.enabled)
    if line is None:
        raise HTTPException(status_code=404, detail="业务线不存在")
    session.commit()
    return ApiResponse(message="业务线状态已更新", data=repo.to_dict(line))


@router.post("/{business_line_id}/delete", response_model=ApiResponse)
async def delete_business_line(business_line_id: str, session: Session = Depends(get_db_session)) -> ApiResponse:
    deleted = BusinessLineRepository(session).delete(business_line_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="业务线不存在")
    session.commit()
    return ApiResponse(message="业务线已删除", data={"business_line_id": business_line_id})


@router.get("/{business_line_id}/embed-code")
async def get_embed_code(
    business_line_id: str,
    request: Request,
    session: Session = Depends(get_db_session),
):
    repo = BusinessLineRepository(session)
    line = repo.get_dict(business_line_id)
    if line is None:
        raise HTTPException(status_code=404, detail="业务线不存在")
    api_base = str(request.base_url).rstrip("/")
    embed_code = (
        f'<script src="{api_base}/static/chat-widget.js?v=20260615-5" '
        f'data-api-base="{api_base}" '
        'data-company-id="default_company" '
        f'data-business-line-id="{business_line_id}"></script>'
    )
    return {
        "business_line_id": business_line_id,
        "business_line_name": line["business_line_name"],
        "bound_knowledge_bases": line["knowledge_bases"],
        "embed_code": embed_code,
    }
