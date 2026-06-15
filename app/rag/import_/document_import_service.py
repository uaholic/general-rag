"""文档导入业务实现。"""
from __future__ import annotations

import json
from pathlib import Path
import re
import shutil
from typing import Any
from urllib.parse import urlparse

from langchain_core.messages import BaseMessage, HumanMessage

from app.infra.llm.providers import llm_provider
from app.infra.object_storage.minio_gateway import minio_gateway
from app.infra.persistence.admin_repositories import DocumentRepository
from app.infra.persistence.mysql import session_scope
from app.rag.import_.markdown_asset_service import markdown_asset_service
from app.rag.import_.pdf_parser_service import IMAGE_EXTENSIONS, PARSED_ROOT, pdf_parser_service
from app.rag.import_.text_utils import TextChunker
from app.shared.config.lm_config import lm_config
from app.shared.runtime.logger import logger


SUPPORTED_TEXT_TYPES = {"txt", "md", "markdown"}
SUPPORTED_PARSE_TYPES = {*SUPPORTED_TEXT_TYPES, "pdf"}
SUBJECT_BATCH_SIZE = 8
SUBJECT_CONTEXT_CHARS = 700
IMAGE_CONTEXT_CHARS = 500
MARKDOWN_IMAGE_WITH_SRC_RE = r"!\[([^\]]*)]\({src}\)"
TECH_TOKEN_RE = re.compile(
    r"[A-Za-z][A-Za-z0-9_+.#/-]{1,30}|[\u4e00-\u9fa5]{2,12}(?:模型|知识库|向量|检索|算法|流程|框架|数据库|技术|服务|系统|业务|图片|文档|课程)"
)


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

    def recognize_chunk_subjects(self, chunks: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """给每个 chunk 识别主体词，供 Milvus metadata 和聊天记录使用。"""
        if not chunks:
            return []

        enriched = [dict(chunk) for chunk in chunks]
        for start in range(0, len(enriched), SUBJECT_BATCH_SIZE):
            batch = enriched[start:start + SUBJECT_BATCH_SIZE]
            try:
                batch_subjects = self._recognize_subject_batch(batch)
            except Exception:
                batch_subjects = {}
            for chunk in batch:
                fallback = self._fallback_subjects(chunk.get("content", ""))
                subjects = self._normalize_subjects(batch_subjects.get(chunk["chunk_id"]) or fallback)
                chunk["subject_names"] = subjects
        return enriched

    def _recognize_subject_batch(self, chunks: list[dict[str, Any]]) -> dict[str, list[str]]:
        payload = [
            {
                "chunk_id": chunk["chunk_id"],
                "text": " ".join((chunk.get("content") or "").split())[:SUBJECT_CONTEXT_CHARS],
            }
            for chunk in chunks
        ]
        prompt = f"""请从每个 chunk 中抽取 3 到 8 个关键主体词。
主体词可以是技术名词、产品名、业务名词、概念名、流程名。
要求：
1. 只返回 JSON，不要解释。
2. JSON 格式为 {{"items":[{{"chunk_id":"...","subject_names":["..."]}}]}}。
3. 每个主体不要超过 20 个字，去重，避免泛泛的“内容”“资料”“问题”。

chunks:
{json.dumps(payload, ensure_ascii=False)}
"""
        llm = llm_provider.chat("qwen-flash", json_mode=True)
        response = llm.invoke(prompt)
        data = self._json_from_response(response)
        result: dict[str, list[str]] = {}
        for item in data.get("items", []):
            chunk_id = str(item.get("chunk_id") or "")
            if chunk_id:
                result[chunk_id] = item.get("subject_names") or []
        return result

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
            summary = self.summarize_image(
                image_url=public_url,
                filename=filename,
                context=self._image_context(markdown_text, source),
            )
            caption = summary or filename
            image_records.append(
                {
                    "filename": filename,
                    "url": public_url,
                    "caption": caption,
                    "alt_text": caption,
                }
            )
            image_url_map[source] = public_url
            image_url_map[filename] = public_url
            image_url_map[public_url] = public_url
            image_url_map[caption] = public_url
            rewritten_text = self._replace_image_source_with_summary(
                text=rewritten_text,
                source=source,
                public_url=public_url,
                summary=caption,
            )

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

    def summarize_image(self, *, image_url: str, filename: str, context: str = "") -> str:
        """使用视觉模型生成一句适合写入 Markdown alt/caption 的图片摘要。"""
        model_candidates = [lm_config.lv_model, "qwen-vl-flash", "qwen-vl-flash-latest"]
        for model_name in [item for item in dict.fromkeys(model_candidates) if item]:
            prompt = (
                "请用中文概括这张知识库图片，输出 1 句 20 到 60 字的说明。"
                "说明要客观描述图片传达的信息，适合放在 Markdown 图片 alt 文案中。"
                f"\n文件名：{filename}"
                f"\n图片附近上下文：{context or '无'}"
            )
            for image_part in (
                {"type": "image_url", "image_url": {"url": image_url}},
                {"type": "image_url", "image_url": image_url},
            ):
                try:
                    llm = llm_provider.vision_chat(model_name)
                    response = llm.invoke(
                        [
                            HumanMessage(
                                content=[
                                    {"type": "text", "text": prompt},
                                    image_part,
                                ]
                            )
                        ]
                    )
                    text = self._message_to_text(response)
                    text = " ".join(text.replace("\n", " ").split())
                    if text:
                        return text[:120]
                except Exception as exc:
                    logger.warning(f"图片摘要生成失败，model={model_name}: {exc}")
        return ""

    @staticmethod
    def _image_context(markdown_text: str, source: str) -> str:
        index = markdown_text.find(source)
        if index < 0:
            return ""
        start = max(0, index - IMAGE_CONTEXT_CHARS)
        end = min(len(markdown_text), index + len(source) + IMAGE_CONTEXT_CHARS)
        return " ".join(markdown_text[start:end].split())

    @staticmethod
    def _replace_image_source_with_summary(*, text: str, source: str, public_url: str, summary: str) -> str:
        clean_summary = " ".join((summary or "文档图片").replace("[", "(").replace("]", ")").split())
        replacement = f"![{clean_summary}]({public_url})"
        pattern = re.compile(MARKDOWN_IMAGE_WITH_SRC_RE.format(src=re.escape(source)))
        replaced = pattern.sub(lambda _match: replacement, text)
        if replaced != text:
            return replaced
        return text.replace(source, public_url)

    @staticmethod
    def _message_to_text(response: Any) -> str:
        if isinstance(response, BaseMessage):
            content = response.content
        else:
            content = response
        if isinstance(content, list):
            parts = []
            for item in content:
                if isinstance(item, dict):
                    parts.append(str(item.get("text") or item.get("content") or ""))
                else:
                    parts.append(str(item))
            return " ".join(part for part in parts if part)
        return str(content or "")

    @classmethod
    def _json_from_response(cls, response: Any) -> dict[str, Any]:
        text = cls._message_to_text(response).strip()
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            match = re.search(r"\{.*}", text, re.S)
            data = json.loads(match.group(0)) if match else {}
        return data if isinstance(data, dict) else {}

    @staticmethod
    def _normalize_subjects(values: list[Any]) -> list[str]:
        subjects: list[str] = []
        banned = {
            "内容",
            "资料",
            "问题",
            "文档",
            "图片",
            "文本",
            "知识",
            "http",
            "https",
            "www",
            "details",
            "left",
            "right",
            "center",
            "figure",
            "image",
            "images",
            "upload",
            "begin",
            "array",
            "leq",
            "geq",
            "cdot",
            "frac",
            "mathrm",
            "operatorname",
            "cases",
            "end",
            "right.",
            "left.",
            "max",
            "min",
        }
        for value in values or []:
            text = str(value).strip().strip("，。、；;:：")
            lowered = text.lower()
            if (
                not text
                or lowered in banned
                or "/" in text
                or lowered.startswith("http")
                or lowered.endswith((".jpg", ".jpeg", ".png", ".webp", ".gif"))
                or re.fullmatch(r"[0-9a-f]{12,}", lowered) is not None
                or (text.isascii() and len(text) <= 2 and text.upper() != "AI")
                or len(text) > 20
            ):
                continue
            if text not in subjects:
                subjects.append(text)
            if len(subjects) >= 8:
                break
        return subjects

    @staticmethod
    def _fallback_subjects(text: str) -> list[str]:
        values: list[str] = []
        banned = {
            "http",
            "https",
            "www",
            "details",
            "left",
            "right",
            "center",
            "figure",
            "image",
            "images",
            "upload",
            "begin",
            "array",
            "leq",
            "geq",
            "cdot",
            "frac",
            "mathrm",
            "operatorname",
            "cases",
            "end",
            "right.",
            "left.",
            "max",
            "min",
        }
        for match in TECH_TOKEN_RE.findall(text or ""):
            token = match.strip()
            lowered = token.lower()
            if (
                "/" in token
                or lowered in banned
                or lowered.startswith("http")
                or lowered.endswith((".jpg", ".jpeg", ".png", ".webp", ".gif"))
                or re.fullmatch(r"[0-9a-f]{12,}", lowered) is not None
                or (token.isascii() and len(token) <= 2 and token.upper() != "AI")
            ):
                continue
            if token and token not in values:
                values.append(token)
            if len(values) >= 6:
                break
        return values

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
