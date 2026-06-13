"""文档管理接口。"""
from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.api.deps import get_db_session
from app.api.frontend import admin_page_response
from app.api.schemas.common import ApiResponse
from app.api.schemas.document import DocumentUploadResponse
from app.infra.persistence.admin_repositories import DocumentRepository, KnowledgeBaseRepository
from app.shared.utils.path_util import PROJECT_ROOT

router = APIRouter(prefix="/admin/documents", tags=["document"])
UPLOAD_ROOT = PROJECT_ROOT / "app" / "resources" / "uploads"


@router.get("", include_in_schema=False)
async def document_page() -> FileResponse:
    return admin_page_response()


@router.get("/list")
async def list_documents(
    kb_id: str | None = Query(None),
    parse_status: str | None = Query(None),
    keyword: str | None = Query(None),
    session: Session = Depends(get_db_session),
):
    return {"items": DocumentRepository(session).list_documents(kb_id=kb_id, parse_status=parse_status, keyword=keyword)}


@router.get("/recent")
async def recent_documents(session: Session = Depends(get_db_session)):
    return {"items": DocumentRepository(session).recent(limit=5)}


@router.get("/{doc_id}")
async def get_document(doc_id: str, session: Session = Depends(get_db_session)):
    repo = DocumentRepository(session)
    document = repo.get(doc_id)
    if document is None:
        raise HTTPException(status_code=404, detail="文档不存在")
    return repo.to_dict(document)


@router.post("/upload", response_model=DocumentUploadResponse)
async def upload_document(
    kb_id: str = Form(...),
    file: UploadFile = File(...),
    session: Session = Depends(get_db_session),
) -> DocumentUploadResponse:
    if KnowledgeBaseRepository(session).get(kb_id) is None:
        raise HTTPException(status_code=404, detail="知识库不存在")

    doc_id = f"doc_{uuid4().hex[:12]}"
    task_id = f"task_{uuid4().hex[:12]}"
    filename = Path(file.filename or "unnamed").name
    file_type = Path(filename).suffix.lstrip(".").lower()
    target_dir = UPLOAD_ROOT / doc_id
    target_dir.mkdir(parents=True, exist_ok=True)
    target_path = target_dir / filename
    target_path.write_bytes(await file.read())

    DocumentRepository(session).create(
        doc_id=doc_id,
        kb_id=kb_id,
        filename=filename,
        file_type=file_type,
        file_path=str(target_path),
        parse_status="pending",
    )
    session.commit()
    return DocumentUploadResponse(doc_id=doc_id, task_id=task_id, message="已保存文档，等待解析实现")


@router.post("/{doc_id}/reparse", response_model=ApiResponse)
async def reparse_document(doc_id: str, session: Session = Depends(get_db_session)) -> ApiResponse:
    repo = DocumentRepository(session)
    document = repo.reset_parse_status(doc_id)
    if document is None:
        raise HTTPException(status_code=404, detail="文档不存在")
    session.commit()
    return ApiResponse(message="已提交重解析占位任务", data=repo.to_dict(document))


@router.post("/{doc_id}/delete", response_model=ApiResponse)
async def delete_document(doc_id: str, session: Session = Depends(get_db_session)) -> ApiResponse:
    repo = DocumentRepository(session)
    document = repo.get(doc_id)
    if document is None:
        raise HTTPException(status_code=404, detail="文档不存在")
    file_path = Path(document.file_path) if document.file_path else None

    deleted = repo.delete(doc_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="文档不存在")
    session.commit()

    if file_path and file_path.exists() and UPLOAD_ROOT in file_path.resolve().parents:
        file_path.unlink(missing_ok=True)
        try:
            file_path.parent.rmdir()
        except OSError:
            pass
    return ApiResponse(message="文档已删除", data={"doc_id": doc_id})
