"""文档导入业务实现。"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from app.infra.persistence.admin_repositories import DocumentRepository
from app.infra.persistence.mysql import session_scope
from app.rag.import_.markdown_asset_service import markdown_asset_service
from app.rag.import_.pdf_parser_service import pdf_parser_service
from app.rag.import_.text_utils import TextChunker


SUPPORTED_TEXT_TYPES = {"txt", "md", "markdown"}
SUPPORTED_PARSE_TYPES = {*SUPPORTED_TEXT_TYPES, "pdf"}


class DocumentImportService:
    """文档导入流程里真正处理业务的类。"""

    def load_document(self, doc_id: str) -> dict[str, Any]:
        """读取文档并标记为 parsing。"""
        with session_scope() as session:
            repo = DocumentRepository(session)
            document = repo.get(doc_id)
            if document is None:
                raise ValueError(f"文档不存在: {doc_id}")

            document.parse_status = "parsing"
            document.error_msg = ""
            session.flush()
            return repo.to_dict(document)

    def parse_source(self, *, doc_id: str, file_path: str, file_type: str) -> dict[str, Any]:
        """把原始文件解析成后续 chunk 可以使用的 Markdown/文本。"""
        normalized_type = (file_type or Path(file_path).suffix.lstrip(".")).lower()
        if normalized_type == "pdf":
            result = pdf_parser_service.parse_pdf(pdf_path=file_path, doc_id=doc_id)
            return {
                "raw_text": result.markdown_text,
                "parsed_md_path": str(result.markdown_path),
                "parsed_image_dir": str(result.image_dir),
                "parser_engine": result.engine,
                "image_count": result.image_count,
            }

        return {
            "raw_text": self.read_text(file_path=file_path, file_type=file_type),
            "parsed_md_path": "",
            "parsed_image_dir": "",
            "parser_engine": "text",
            "image_count": 0,
        }

    def read_text(self, *, file_path: str, file_type: str) -> str:
        """读取 txt/md 文本。"""
        normalized_type = (file_type or Path(file_path).suffix.lstrip(".")).lower()
        if normalized_type not in SUPPORTED_TEXT_TYPES:
            raise NotImplementedError(f"暂未实现 {normalized_type or '未知'} 文件解析，请先练习 txt/md/pdf")

        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"文档文件不存在: {path}")

        # 先用 utf-8，读失败再降级到 utf-8-sig。后续可以补 chardet 或 charset-normalizer。
        try:
            return path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            return path.read_text(encoding="utf-8-sig")

    def inspect_markdown_assets(self, *, text: str, file_path: str, file_type: str) -> dict[str, Any]:
        """识别 Markdown 图片引用。

        TODO: 后续接 zip/目录上传后，在这里把本地图片保存到对象存储，并重写 Markdown。
        """
        normalized_type = (file_type or Path(file_path).suffix.lstrip(".")).lower()
        if normalized_type not in {"md", "markdown"}:
            return {"markdown_image_refs": [], "asset_warnings": []}
        return markdown_asset_service.inspect(markdown_text=text, markdown_path=file_path)

    def split_text(
        self,
        *,
        doc_id: str,
        kb_id: str,
        filename: str,
        text: str,
        chunk_size: int = 800,
        chunk_overlap: int = 120,
    ) -> list[dict[str, Any]]:
        """切分文本并补齐后续写 Milvus 需要的 metadata。"""
        chunker = TextChunker(chunk_size=chunk_size, chunk_overlap=chunk_overlap)
        chunks = chunker.split(text)
        return [
            {
                "chunk_id": f"{doc_id}_{chunk.index}",
                "doc_id": doc_id,
                "kb_id": kb_id,
                "filename": filename,
                "chunk_index": chunk.index,
                "content": chunk.content,
                "title": filename,
                "title_path": filename,
                "subject_names": [],
                "image_urls": [],
            }
            for chunk in chunks
        ]

    def mark_success(self, *, doc_id: str, chunk_count: int, image_count: int = 0) -> dict[str, Any]:
        """导入成功后更新 document 和知识库统计。"""
        with session_scope() as session:
            repo = DocumentRepository(session)
            document = repo.get(doc_id)
            if document is None:
                raise ValueError(f"文档不存在: {doc_id}")

            document.parse_status = "success"
            document.error_msg = ""
            document.chunk_count = chunk_count
            document.image_count = image_count
            session.flush()
            repo._refresh_kb_counts(document.kb_id)
            session.flush()
            return repo.to_dict(document)

    def mark_failed(self, *, doc_id: str, error: str) -> dict[str, Any] | None:
        """导入失败后记录错误，给前端详情弹窗展示。"""
        with session_scope() as session:
            repo = DocumentRepository(session)
            document = repo.get(doc_id)
            if document is None:
                return None

            document.parse_status = "failed"
            document.error_msg = error[:2000]
            document.chunk_count = 0
            document.image_count = 0
            session.flush()
            repo._refresh_kb_counts(document.kb_id)
            session.flush()
            return repo.to_dict(document)


document_import_service = DocumentImportService()
