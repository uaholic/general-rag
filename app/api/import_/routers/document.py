"""文档管理接口。"""
from __future__ import annotations

from pathlib import Path
from threading import Thread
from uuid import uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.api.deps import get_db_session
from app.api.frontend import admin_page_response
from app.api.schemas.common import ApiResponse
from app.api.schemas.document import DocumentUploadResponse
from app.infra.object_storage.minio_gateway import minio_gateway
from app.infra.persistence.admin_repositories import DocumentRepository, KnowledgeBaseRepository
from app.process.import_.agent.main_graph import run_import_graph
from app.process.import_.task_store import get_import_task_by_doc, start_import_task
from app.rag.import_.pdf_parser_service import pdf_parser_service
from app.rag.import_.vector_writer import vector_write_service
from app.shared.runtime.logger import logger
from app.shared.utils.path_util import PROJECT_ROOT

router = APIRouter(prefix="/admin/documents", tags=["document"])
UPLOAD_ROOT = PROJECT_ROOT / "app" / "resources" / "uploads"
PARSABLE_FILE_TYPES = {"txt", "md", "markdown", "pdf"}


def _new_task_id(prefix: str = "task") -> str:
    return f"{prefix}_{uuid4().hex[:12]}"


def _attach_task(item: dict) -> dict:
    task = get_import_task_by_doc(item.get("doc_id", ""))
    if task:
        item = {**item, "task": task}
    return item


def _run_import_background(doc_id: str, task_id: str) -> None:
    try:
        run_import_graph(
            doc_id=doc_id,
            task_id=task_id,
            run_embedding=True,
            write_milvus=True,
        )
    except Exception:
        logger.exception(f"文档后台导入失败 doc_id={doc_id} task_id={task_id}")


def _start_import_background(doc_id: str, task_id: str) -> None:
    Thread(
        target=_run_import_background,
        args=(doc_id, task_id),
        name=f"document-import-{doc_id}",
        daemon=True,
    ).start()


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
    items = DocumentRepository(session).list_documents(kb_id=kb_id, parse_status=parse_status, keyword=keyword)
    return {"items": [_attach_task(item) for item in items]}


@router.get("/recent")
async def recent_documents(session: Session = Depends(get_db_session)):
    return {"items": [_attach_task(item) for item in DocumentRepository(session).recent(limit=5)]}


@router.get("/{doc_id}")
async def get_document(doc_id: str, session: Session = Depends(get_db_session)):
    repo = DocumentRepository(session)
    document = repo.get(doc_id)
    if document is None:
        raise HTTPException(status_code=404, detail="文档不存在")
    return _attach_task(repo.to_dict(document))


@router.get("/{doc_id}/task")
async def get_document_task(doc_id: str, session: Session = Depends(get_db_session)):
    document = DocumentRepository(session).get(doc_id)
    if document is None:
        raise HTTPException(status_code=404, detail="文档不存在")
    task = get_import_task_by_doc(doc_id)
    if task:
        return task
    return {
        "task_id": "",
        "doc_id": doc_id,
        "status": document.parse_status,
        "progress": [],
        "message": document.error_msg or document.parse_status,
        "error_msg": document.error_msg or "",
        "started_at": "",
        "updated_at": document.updated_at.isoformat(timespec="seconds") if document.updated_at else "",
        "finished_at": "",
    }


@router.post("/upload", response_model=DocumentUploadResponse)
async def upload_document(
    kb_id: str = Form(...),
    file: UploadFile = File(...),
    session: Session = Depends(get_db_session),
) -> DocumentUploadResponse:
    if KnowledgeBaseRepository(session).get(kb_id) is None:
        raise HTTPException(status_code=404, detail="知识库不存在")

    doc_id = f"doc_{uuid4().hex[:12]}"
    task_id = ""
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

    message = "已保存文档；当前文件类型暂不支持自动解析"
    if file_type in PARSABLE_FILE_TYPES:
        task_id = _new_task_id()
        start_import_task(task_id=task_id, doc_id=doc_id)
        _start_import_background(doc_id, task_id)
        message = "已上传文档，后台解析和向量入库已开始"
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
        task_id = _new_task_id("reparse")
        start_import_task(task_id=task_id, doc_id=doc_id)
        _start_import_background(doc_id, task_id)
        return ApiResponse(message="已提交后台重解析和向量入库", data={"doc_id": doc_id, "task_id": task_id})
    return ApiResponse(message="已重置为待解析；当前文件类型暂不支持自动解析", data={"doc_id": doc_id})


@router.post("/{doc_id}/delete", response_model=ApiResponse)
async def delete_document(doc_id: str, session: Session = Depends(get_db_session)) -> ApiResponse:
    repo = DocumentRepository(session)
    document = repo.get(doc_id)
    if document is None:
        raise HTTPException(status_code=404, detail="文档不存在")
    file_path = Path(document.file_path) if document.file_path else None
    filename = document.filename

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
    try:
        minio_gateway.clear_file_dir(filename)
    except Exception:
        logger.exception(f"删除文档 MinIO 目录失败 doc_id={doc_id} filename={filename}")
    try:
        vector_write_service.delete_document_chunks(doc_id)
    except Exception:
        logger.exception(f"删除文档 Milvus chunk 失败 doc_id={doc_id}")
    return ApiResponse(message="文档已删除", data={"doc_id": doc_id})
