"""文档导入业务实现。"""
from __future__ import annotations

from pathlib import Path
import shutil
from typing import Any
from urllib.parse import urlparse

from app.infra.object_storage.minio_gateway import minio_gateway
from app.infra.persistence.admin_repositories import DocumentRepository
from app.infra.persistence.mysql import session_scope
from app.rag.import_.markdown_asset_service import markdown_asset_service
from app.rag.import_.pdf_parser_service import IMAGE_EXTENSIONS, PARSED_ROOT, pdf_parser_service
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
        source_path = Path(file_path)
        source_filename = source_path.name
        minio_gateway.clear_file_dir(source_filename)
        minio_url = minio_gateway.upload_file(
            local_path=source_path,
            filename=source_filename,
            relative_name=f"source/{source_filename}",
        )
        if normalized_type == "pdf":
            result = pdf_parser_service.parse_pdf(pdf_path=file_path, doc_id=doc_id)
            image_bundle = self.prepare_markdown_images(
                doc_id=doc_id,
                markdown_text=result.markdown_text,
                markdown_path=str(result.markdown_path),
                upload_filename=source_filename,
            )
            if image_bundle["rewritten_text"] != result.markdown_text:
                result.markdown_path.write_text(image_bundle["rewritten_text"], encoding="utf-8")
            parsed_md_minio_url = minio_gateway.upload_file(
                local_path=result.markdown_path,
                filename=source_filename,
                relative_name=f"parsed/{result.markdown_path.name}",
            )
            return {
                "raw_text": image_bundle["rewritten_text"],
                "parsed_md_path": str(result.markdown_path),
                "parsed_md_minio_url": parsed_md_minio_url,
                "parsed_image_dir": str(result.image_dir),
                "parser_engine": result.engine,
                "minio_url": minio_url,
                "image_count": len(image_bundle["image_records"]),
                "image_records": image_bundle["image_records"],
                "image_url_map": image_bundle["image_url_map"],
            }

        raw_text = self.read_text(file_path=file_path, file_type=file_type)
        image_bundle = (
            self.prepare_markdown_images(
                doc_id=doc_id,
                markdown_text=raw_text,
                markdown_path=file_path,
                upload_filename=source_filename,
            )
            if normalized_type in {"md", "markdown"}
            else {"rewritten_text": raw_text, "image_records": [], "image_url_map": {}}
        )
        return {
            "raw_text": image_bundle["rewritten_text"],
            "parsed_md_path": "",
            "parsed_md_minio_url": "",
            "parsed_image_dir": "",
            "parser_engine": "text",
            "minio_url": minio_url,
            "image_count": len(image_bundle["image_records"]),
            "image_records": image_bundle["image_records"],
            "image_url_map": image_bundle["image_url_map"],
        }

    def read_text(self, *, file_path: str, file_type: str) -> str:
        """读取 txt/md 文本。"""
        normalized_type = (file_type or Path(file_path).suffix.lstrip(".")).lower()
        if normalized_type not in SUPPORTED_TEXT_TYPES:
            raise NotImplementedError(f"暂不支持 {normalized_type or '未知'} 文件解析；当前支持 txt、md、pdf")

        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"文档文件不存在: {path}")

        try:
            return path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            return path.read_text(encoding="utf-8-sig")

    def inspect_markdown_assets(self, *, text: str, file_path: str, file_type: str) -> dict[str, Any]:
        """识别 Markdown 图片引用。
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
        image_url_map: dict[str, str] | None = None,
        chunk_size: int = 800,
        chunk_overlap: int = 120,
    ) -> list[dict[str, Any]]:
        """切分文本并补齐后续写 Milvus 需要的 metadata。"""
        chunker = TextChunker(chunk_size=chunk_size, chunk_overlap=chunk_overlap)
        chunks = chunker.split(text)
        url_map = image_url_map or {}
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
                "image_urls": self._image_urls_for_text(chunk.content, url_map),
            }
            for chunk in chunks
        ]

    def prepare_markdown_images(
        self,
        *,
        doc_id: str,
        markdown_text: str,
        markdown_path: str,
        upload_filename: str,
    ) -> dict[str, Any]:
        """把 Markdown 中可访问的图片上传到 MinIO，并替换为前端可访问 URL。"""
        sources = markdown_asset_service._extract_sources(markdown_text)
        if not sources:
            return {"rewritten_text": markdown_text, "image_records": [], "image_url_map": {}}

        base_dir = Path(markdown_path).parent
        rewritten_text = markdown_text
        image_records: list[dict[str, Any]] = []
        image_url_map: dict[str, str] = {}

        for source in sources:
            public_url = self._resolve_image_url(
                doc_id=doc_id,
                source=source,
                base_dir=base_dir,
                upload_filename=upload_filename,
            )
            if not public_url:
                continue
            filename = Path(urlparse(public_url).path).name or Path(source).name or "image"
            image_records.append(
                {
                    "filename": filename,
                    "url": public_url,
                    "caption": filename,
                    "alt_text": filename,
                }
            )
            image_url_map[source] = public_url
            image_url_map[filename] = public_url
            image_url_map[public_url] = public_url
            rewritten_text = rewritten_text.replace(source, public_url)

        return {
            "rewritten_text": rewritten_text,
            "image_records": image_records,
            "image_url_map": image_url_map,
        }

    def _resolve_image_url(self, *, doc_id: str, source: str, base_dir: Path, upload_filename: str) -> str:
        parsed = urlparse(source)
        if parsed.scheme in {"http", "https"}:
            return source
        if parsed.scheme in {"data", "file"}:
            return ""

        source_path = Path(source)
        if source_path.is_absolute():
            return ""
        resolved = (base_dir / source_path).resolve()
        if not resolved.exists() or not resolved.is_file() or resolved.suffix.lower() not in IMAGE_EXTENSIONS:
            return ""

        doc_dir = (PARSED_ROOT / doc_id).resolve()
        if not resolved.is_relative_to(doc_dir):
            assets_dir = doc_dir / "assets"
            assets_dir.mkdir(parents=True, exist_ok=True)
            target = self._unique_target(assets_dir, resolved.name)
            shutil.copy2(resolved, target)
            resolved = target.resolve()

        rel_path = resolved.relative_to(doc_dir).as_posix()
        return minio_gateway.upload_file(
            local_path=resolved,
            filename=upload_filename,
            relative_name=f"images/{rel_path}",
        )

    @staticmethod
    def _unique_target(directory: Path, filename: str) -> Path:
        stem = Path(filename).stem or "image"
        suffix = Path(filename).suffix or ".png"
        target = directory / f"{stem}{suffix}"
        index = 1
        while target.exists():
            target = directory / f"{stem}_{index}{suffix}"
            index += 1
        return target

    @staticmethod
    def _image_urls_for_text(text: str, image_url_map: dict[str, str]) -> list[str]:
        urls: list[str] = []
        for marker, url in image_url_map.items():
            if marker and marker in text and url not in urls:
                urls.append(url)
        return urls

    def mark_success(
        self,
        *,
        doc_id: str,
        chunk_count: int,
        image_count: int = 0,
        image_records: list[dict[str, Any]] | None = None,
        minio_url: str = "",
    ) -> dict[str, Any]:
        """导入成功后更新 document 和知识库统计。"""
        with session_scope() as session:
            repo = DocumentRepository(session)
            document = repo.get(doc_id)
            if document is None:
                raise ValueError(f"文档不存在: {doc_id}")

            if image_records is not None:
                image_count = repo.replace_images(document, image_records)
            document.parse_status = "success"
            document.error_msg = ""
            document.chunk_count = chunk_count
            document.image_count = image_count
            if minio_url:
                document.minio_url = minio_url
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
            repo.clear_images(doc_id)
            session.flush()
            repo._refresh_kb_counts(document.kb_id)
            session.flush()
            return repo.to_dict(document)


document_import_service = DocumentImportService()
