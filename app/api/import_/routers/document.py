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
from app.process.import_.agent.main_graph import run_import_graph
from app.rag.import_.pdf_parser_service import pdf_parser_service
from app.shared.utils.path_util import PROJECT_ROOT

router = APIRouter(prefix="/admin/documents", tags=["document"])
UPLOAD_ROOT = PROJECT_ROOT / "app" / "resources" / "uploads"
PARSABLE_FILE_TYPES = {"txt", "md", "markdown", "pdf"}


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

    message = "已保存文档，当前文件类型的解析流程待实现"
    if file_type in PARSABLE_FILE_TYPES:
        try:
            state = run_import_graph(doc_id=doc_id, task_id=task_id)
            warning_count = len(state.get("asset_warnings", []))
            message = (
                f"已保存文档，并完成基础解析；发现 {warning_count} 个本地图片引用未处理"
                if warning_count
                else "已保存文档，并完成基础解析"
            )
        except Exception as exc:
            message = f"已保存文档，但基础解析失败：{exc}"
    return DocumentUploadResponse(doc_id=doc_id, task_id=task_id, message=message)


@router.post("/{doc_id}/reparse", response_model=ApiResponse)
async def reparse_document(doc_id: str, session: Session = Depends(get_db_session)) -> ApiResponse:
    repo = DocumentRepository(session)
    document = repo.reset_parse_status(doc_id)
    if document is None:
        raise HTTPException(status_code=404, detail="文档不存在")
    file_type = (document.file_type or "").lower()
    session.commit()
    if file_type in PARSABLE_FILE_TYPES:
        try:
            state = run_import_graph(doc_id=doc_id, task_id=f"reparse_{doc_id}")
            warning_count = len(state.get("asset_warnings", []))
            if warning_count:
                return ApiResponse(message=f"基础重解析完成；发现 {warning_count} 个本地图片引用未处理", data=state)
            return ApiResponse(message="基础重解析完成", data=state)
        except Exception as exc:
            return ApiResponse(success=False, message=f"基础重解析失败：{exc}", data={"doc_id": doc_id})
    return ApiResponse(message="已重置为待解析，当前文件类型的解析流程待实现", data={"doc_id": doc_id})


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
    pdf_parser_service.delete_parsed(doc_id)
    return ApiResponse(message="文档已删除", data={"doc_id": doc_id})
