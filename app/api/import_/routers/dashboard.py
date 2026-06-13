"""后台概览接口。"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_db_session
from app.infra.persistence.admin_repositories import DashboardRepository

router = APIRouter(prefix="/admin/dashboard", tags=["dashboard"])


@router.get("/summary")
async def summary(session: Session = Depends(get_db_session)):
    return DashboardRepository(session).summary()
