"""聊天框配置接口。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.deps import get_db_session
from app.api.schemas.chat import WidgetConfigResponse
from app.infra.persistence.admin_repositories import BusinessLineRepository, SystemConfigRepository

router = APIRouter(prefix="/api", tags=["widget"])


@router.get("/widget/config", response_model=WidgetConfigResponse)
async def get_widget_config(
    business_line_id: str = Query(...),
    company_id: str = Query("default_company"),
    theme_color: str | None = Query(None),
    session: Session = Depends(get_db_session),
) -> WidgetConfigResponse:
    _ = company_id
    company_repo = SystemConfigRepository(session)
    line_repo = BusinessLineRepository(session)
    company = company_repo.get_default()
    line = line_repo.get_dict(business_line_id)
    if line is None or not line["enabled"]:
        raise HTTPException(status_code=404, detail="业务线不存在或已停用")
    return WidgetConfigResponse(
        company_name=company.company_name,
        business_line_id=business_line_id,
        business_line_name=line["business_line_name"],
        welcome_message=line["welcome_message"] or company.welcome_message or "你好，我是知识库助手，可以帮你查询资料。",
        fallback_message=line["fallback_message"] or company.fallback_message or "抱歉，当前知识库中没有找到明确依据。",
        bound_kb_ids=line["kb_ids"],
        theme_color=theme_color or "#2563eb",
    )
