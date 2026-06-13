"""企业信息配置接口。"""
from __future__ import annotations

from fastapi import APIRouter
from fastapi import Depends
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.api.deps import get_db_session
from app.api.frontend import admin_page_response
from app.api.schemas.common import ApiResponse
from app.api.schemas.company import CompanySaveRequest
from app.infra.persistence.admin_repositories import SystemConfigRepository

router = APIRouter(prefix="/admin/company", tags=["company"])


@router.get("", include_in_schema=False)
async def company_page() -> FileResponse:
    return admin_page_response()


@router.get("/data")
async def get_company(session: Session = Depends(get_db_session)):
    repo = SystemConfigRepository(session)
    return repo.to_dict(repo.get_default())


@router.post("/save", response_model=ApiResponse)
async def save_company(payload: CompanySaveRequest, session: Session = Depends(get_db_session)) -> ApiResponse:
    repo = SystemConfigRepository(session)
    config = repo.save_default(payload.model_dump())
    session.commit()
    return ApiResponse(message="企业配置已保存", data=repo.to_dict(config))
