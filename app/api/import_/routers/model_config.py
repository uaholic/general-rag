"""模型配置接口。"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.api.deps import get_db_session
from app.api.frontend import admin_page_response
from app.api.schemas.common import ApiResponse
from app.api.schemas.model_config import ModelConfigSaveRequest
from app.infra.persistence.admin_repositories import ModelConfigRepository

router = APIRouter(prefix="/admin/models", tags=["model-config"])


@router.get("", include_in_schema=False)
async def model_config_page() -> FileResponse:
    return admin_page_response()


@router.get("/data")
async def get_model_config(session: Session = Depends(get_db_session)):
    repo = ModelConfigRepository(session)
    return repo.to_dict(repo.get_default())


@router.post("/save", response_model=ApiResponse)
async def save_model_config(payload: ModelConfigSaveRequest, session: Session = Depends(get_db_session)) -> ApiResponse:
    repo = ModelConfigRepository(session)
    config = repo.save_default(payload.model_dump())
    session.commit()
    return ApiResponse(message="模型配置已保存", data=repo.to_dict(config))
