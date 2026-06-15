"""管理端基础配置 Repository。"""
from __future__ import annotations

import re
from uuid import uuid4

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.infra.persistence.models import (
    BusinessLineConfig,
    BusinessLineKnowledgeBase,
    Document,
    DocumentImage,
    KnowledgeBase,
    ModelConfig,
    SystemConfig,
)
from app.shared.config.lm_config import lm_config


DEFAULT_CONFIG_ID = "default"


def _compact_id(prefix: str, raw: str | None = None) -> str:
    source = re.sub(r"[^a-zA-Z0-9_]+", "_", raw or "").strip("_").lower()
    if source:
        return f"{prefix}_{source}"[:64]
    return f"{prefix}_{uuid4().hex[:12]}"


def _bool(value: bool | int | None) -> bool:
    return bool(value)


class SystemConfigRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_default(self) -> SystemConfig:
        config = self.session.get(SystemConfig, DEFAULT_CONFIG_ID)
        if config is None:
            config = SystemConfig(
                id=DEFAULT_CONFIG_ID,
                company_name="XX智能科技有限公司",
                industry="AI 教育 / 大模型学习",
                company_description="专注于大模型、RAG、Agent、AI 应用开发教学与实践。",
                business_scope="大模型课程、RAG 项目训练、AI 工具开发。",
                answer_tone="专业、清晰、适合初学者理解",
                welcome_message="你好，我是课程知识库助手，可以帮你解答大模型学习问题。",
                fallback_message="抱歉，当前知识库中没有找到明确依据。",
                disclaimer="回答仅基于已上传资料，不代表完整官方文档解释。",
            )
            self.session.add(config)
            self.session.flush()
        return config

    def save_default(self, data: dict) -> SystemConfig:
        config = self.get_default()
        for field in (
            "company_name",
            "industry",
            "company_description",
            "business_scope",
            "answer_tone",
            "welcome_message",
            "fallback_message",
            "disclaimer",
        ):
            if field in data:
                setattr(config, field, data[field])
        self.session.flush()
        return config

    @staticmethod
    def to_dict(config: SystemConfig) -> dict:
        return {
            "id": config.id,
            "company_name": config.company_name,
            "industry": config.industry or "",
            "company_description": config.company_description or "",
            "business_scope": config.business_scope or "",
            "answer_tone": config.answer_tone or "",
            "welcome_message": config.welcome_message or "",
            "fallback_message": config.fallback_message or "",
            "disclaimer": config.disclaimer or "",
        }


class BusinessLineRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def list_with_kbs(self) -> list[dict]:
        lines = list(self.session.scalars(select(BusinessLineConfig).order_by(BusinessLineConfig.id.desc())).all())
        return [self.to_dict(line) for line in lines]

    def get(self, business_line_id: str) -> BusinessLineConfig | None:
        return self.session.get(BusinessLineConfig, business_line_id)

    def get_dict(self, business_line_id: str) -> dict | None:
        line = self.get(business_line_id)
        return self.to_dict(line) if line else None

    def save(self, data: dict) -> BusinessLineConfig:
        business_line_id = data.get("business_line_id") or data.get("id") or _compact_id("business_line", data.get("business_line_name"))
        line = self.get(business_line_id)
        if line is None:
            line = BusinessLineConfig(id=business_line_id, business_line_name=data["business_line_name"])
            self.session.add(line)

        line.business_line_name = data["business_line_name"]
        line.business_line_description = data.get("business_line_description") or ""
        line.scenario = data.get("scenario") or ""
        line.target_user = data.get("target_user") or ""
        line.assistant_role = data.get("assistant_role") or ""
        line.welcome_message = data.get("welcome_message") or ""
        line.fallback_message = data.get("fallback_message") or ""
        line.prompt_extra = data.get("prompt_extra") or ""
        line.enabled = _bool(data.get("enabled", True))

        self.session.flush()
        self.replace_bindings(line.id, data.get("kb_ids") or [])
        self.session.flush()
        return line

    def replace_bindings(self, business_line_id: str, kb_ids: list[str]) -> None:
        self.session.execute(
            delete(BusinessLineKnowledgeBase).where(BusinessLineKnowledgeBase.business_line_id == business_line_id)
        )
        valid_ids = list(
            self.session.scalars(
                select(KnowledgeBase.kb_id)
                .where(KnowledgeBase.kb_id.in_(kb_ids))
                .where(KnowledgeBase.enabled.is_(True))
            ).all()
        )
        for kb_id in valid_ids:
            self.session.add(BusinessLineKnowledgeBase(business_line_id=business_line_id, kb_id=kb_id))

    def toggle(self, business_line_id: str, enabled: bool) -> BusinessLineConfig | None:
        line = self.get(business_line_id)
        if line is None:
            return None
        line.enabled = enabled
        self.session.flush()
        return line

    def delete(self, business_line_id: str) -> bool:
        line = self.get(business_line_id)
        if line is None:
            return False
        self.session.execute(
            delete(BusinessLineKnowledgeBase).where(BusinessLineKnowledgeBase.business_line_id == business_line_id)
        )
        self.session.delete(line)
        self.session.flush()
        return True

    def bound_kbs(self, business_line_id: str) -> list[KnowledgeBase]:
        statement = (
            select(KnowledgeBase)
            .join(BusinessLineKnowledgeBase, BusinessLineKnowledgeBase.kb_id == KnowledgeBase.kb_id)
            .where(BusinessLineKnowledgeBase.business_line_id == business_line_id)
            .where(KnowledgeBase.enabled.is_(True))
            .order_by(KnowledgeBase.kb_id.desc())
        )
        return list(self.session.scalars(statement).all())

    def to_dict(self, line: BusinessLineConfig) -> dict:
        kbs = self.bound_kbs(line.id)
        return {
            "business_line_id": line.id,
            "business_line_name": line.business_line_name,
            "business_line_description": line.business_line_description or "",
            "scenario": line.scenario or "",
            "target_user": line.target_user or "",
            "assistant_role": line.assistant_role or "",
            "welcome_message": line.welcome_message or "",
            "fallback_message": line.fallback_message or "",
            "prompt_extra": line.prompt_extra or "",
            "enabled": _bool(line.enabled),
            "kb_ids": [kb.kb_id for kb in kbs],
            "knowledge_bases": [KnowledgeBaseRepository.to_dict(kb, business_lines=[]) for kb in kbs],
        }


class KnowledgeBaseRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def list_with_business_lines(self) -> list[dict]:
        kbs = list(self.session.scalars(select(KnowledgeBase).order_by(KnowledgeBase.kb_id.desc())).all())
        return [self.to_dict(kb, self.bound_business_lines(kb.kb_id)) for kb in kbs]

    def get(self, kb_id: str) -> KnowledgeBase | None:
        return self.session.get(KnowledgeBase, kb_id)

    def save(self, data: dict, kb_id: str | None = None) -> KnowledgeBase:
        current_id = kb_id or data.get("kb_id") or _compact_id("kb", data.get("name"))
        kb = self.get(current_id)
        if kb is None:
            kb = KnowledgeBase(kb_id=current_id, name=data["name"])
            self.session.add(kb)
        kb.name = data["name"]
        kb.description = data.get("description") or ""
        kb.enabled = _bool(data.get("enabled", True))
        self.session.flush()
        if not kb.enabled:
            self.unbind_all(kb.kb_id)
            self.session.flush()
        return kb

    def toggle(self, kb_id: str, enabled: bool) -> KnowledgeBase | None:
        kb = self.get(kb_id)
        if kb is None:
            return None
        kb.enabled = enabled
        self.session.flush()
        if not enabled:
            self.unbind_all(kb_id)
            self.session.flush()
        return kb

    def unbind_all(self, kb_id: str) -> int:
        result = self.session.execute(delete(BusinessLineKnowledgeBase).where(BusinessLineKnowledgeBase.kb_id == kb_id))
        return int(result.rowcount or 0)

    def unbind_disabled(self) -> int:
        disabled_kbs = select(KnowledgeBase.kb_id).where(KnowledgeBase.enabled.is_(False))
        result = self.session.execute(delete(BusinessLineKnowledgeBase).where(BusinessLineKnowledgeBase.kb_id.in_(disabled_kbs)))
        return int(result.rowcount or 0)

    def disabled_or_missing(self, kb_ids: list[str]) -> list[dict]:
        unique_ids = list(dict.fromkeys(kb_ids))
        if not unique_ids:
            return []
        statement = select(KnowledgeBase).where(KnowledgeBase.kb_id.in_(unique_ids))
        found = {kb.kb_id: kb for kb in self.session.scalars(statement).all()}
        invalid = []
        for kb_id in unique_ids:
            kb = found.get(kb_id)
            if kb is None:
                invalid.append({"kb_id": kb_id, "name": kb_id, "reason": "不存在"})
            elif not _bool(kb.enabled):
                invalid.append({"kb_id": kb_id, "name": kb.name, "reason": "已停用"})
        return invalid

    def delete(self, kb_id: str) -> bool:
        kb = self.get(kb_id)
        if kb is None:
            return False
        self.session.execute(delete(BusinessLineKnowledgeBase).where(BusinessLineKnowledgeBase.kb_id == kb_id))
        self.session.delete(kb)
        self.session.flush()
        return True

    def bound_business_lines(self, kb_id: str) -> list[BusinessLineConfig]:
        kb = self.get(kb_id)
        if kb is not None and not _bool(kb.enabled):
            return []
        statement = (
            select(BusinessLineConfig)
            .join(BusinessLineKnowledgeBase, BusinessLineKnowledgeBase.business_line_id == BusinessLineConfig.id)
            .where(BusinessLineKnowledgeBase.kb_id == kb_id)
            .order_by(BusinessLineConfig.id.desc())
        )
        return list(self.session.scalars(statement).all())

    @staticmethod
    def to_dict(kb: KnowledgeBase, business_lines: list[BusinessLineConfig] | None = None) -> dict:
        return {
            "kb_id": kb.kb_id,
            "name": kb.name,
            "description": kb.description or "",
            "enabled": _bool(kb.enabled),
            "doc_count": kb.doc_count,
            "chunk_count": kb.chunk_count,
            "business_lines": [
                {
                    "business_line_id": line.id,
                    "business_line_name": line.business_line_name,
                    "enabled": _bool(line.enabled),
                }
                for line in (business_lines or [])
            ],
        }


class ModelConfigRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_default(self) -> ModelConfig:
        config = self.session.get(ModelConfig, DEFAULT_CONFIG_ID)
        default_llm_model = lm_config.llm_model or "qwen-flash"
        if config is None:
            config = ModelConfig(
                id=DEFAULT_CONFIG_ID,
                llm_model_name=default_llm_model,
                embedding_model_name="BGE-M3",
                rerank_model_name="BGE Reranker",
                image_model_name="Qwen-Flash",
                top_k=5,
                use_rerank=False,
            )
            self.session.add(config)
            self.session.flush()
        elif config.llm_model_name in {"", "gpt-4o-mini"} and lm_config.llm_model:
            config.llm_model_name = default_llm_model
            self.session.flush()
        return config

    def save_default(self, data: dict) -> ModelConfig:
        config = self.get_default()
        for field in (
            "llm_model_name",
            "embedding_model_name",
            "rerank_model_name",
            "image_model_name",
            "top_k",
            "use_rerank",
        ):
            if field in data:
                setattr(config, field, data[field])
        self.session.flush()
        return config

    @staticmethod
    def to_dict(config: ModelConfig) -> dict:
        return {
            "id": config.id,
            "llm_model_name": config.llm_model_name or "",
            "embedding_model_name": config.embedding_model_name or "",
            "rerank_model_name": config.rerank_model_name or "",
            "image_model_name": config.image_model_name or "",
            "top_k": config.top_k,
            "use_rerank": _bool(config.use_rerank),
        }


class DashboardRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def summary(self) -> dict:
        return {
            "business_line_count": self.session.scalar(select(func.count()).select_from(BusinessLineConfig)) or 0,
            "knowledge_base_count": self.session.scalar(select(func.count()).select_from(KnowledgeBase)) or 0,
            "document_count": self.session.scalar(select(func.count()).select_from(Document)) or 0,
            "chunk_count": self.session.scalar(select(func.coalesce(func.sum(Document.chunk_count), 0))) or 0,
            "session_count": 0,
        }


class DocumentRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def list_documents(
        self,
        *,
        kb_id: str | None = None,
        parse_status: str | None = None,
        keyword: str | None = None,
        limit: int = 100,
    ) -> list[dict]:
        statement = select(Document)
        if kb_id:
            statement = statement.where(Document.kb_id == kb_id)
        if parse_status:
            statement = statement.where(Document.parse_status == parse_status)
        if keyword:
            statement = statement.where(Document.filename.like(f"%{keyword}%"))
        statement = statement.order_by(Document.updated_at.desc(), Document.doc_id.desc()).limit(limit)
        return [self.to_dict(document) for document in self.session.scalars(statement).all()]

    def recent(self, limit: int = 5) -> list[dict]:
        statement = select(Document).order_by(Document.updated_at.desc(), Document.doc_id.desc()).limit(limit)
        return [self.to_dict(document) for document in self.session.scalars(statement).all()]

    def get(self, doc_id: str) -> Document | None:
        return self.session.get(Document, doc_id)

    def create(
        self,
        *,
        doc_id: str,
        kb_id: str,
        filename: str,
        file_type: str,
        file_path: str,
        minio_url: str = "",
        parse_status: str = "pending",
    ) -> Document:
        document = Document(
            doc_id=doc_id,
            kb_id=kb_id,
            filename=filename,
            file_type=file_type,
            file_path=file_path,
            minio_url=minio_url,
            parse_status=parse_status,
            chunk_count=0,
            image_count=0,
        )
        self.session.add(document)
        self.session.flush()
        self._refresh_kb_counts(kb_id)
        self.session.flush()
        return document

    def reset_parse_status(self, doc_id: str) -> Document | None:
        document = self.get(doc_id)
        if document is None:
            return None
        document.parse_status = "pending"
        document.error_msg = ""
        document.chunk_count = 0
        document.image_count = 0
        document.minio_url = ""
        self.clear_images(doc_id)
        self.session.flush()
        self._refresh_kb_counts(document.kb_id)
        self.session.flush()
        return document

    def delete(self, doc_id: str) -> bool:
        document = self.get(doc_id)
        if document is None:
            return False
        kb_id = document.kb_id
        self.clear_images(doc_id)
        self.session.delete(document)
        self.session.flush()
        self._refresh_kb_counts(kb_id)
        self.session.flush()
        return True

    def clear_images(self, doc_id: str) -> int:
        result = self.session.execute(delete(DocumentImage).where(DocumentImage.doc_id == doc_id))
        return int(result.rowcount or 0)

    def replace_images(self, document: Document, image_records: list[dict]) -> int:
        self.clear_images(document.doc_id)
        unique_records: list[dict] = []
        seen_urls: set[str] = set()
        for record in image_records:
            url = record.get("url") or record.get("minio_url") or ""
            if not url or url in seen_urls:
                continue
            seen_urls.add(url)
            unique_records.append(record)

        for index, record in enumerate(unique_records, start=1):
            self.session.add(
                DocumentImage(
                    image_id=record.get("image_id") or f"img_{uuid4().hex[:12]}",
                    doc_id=document.doc_id,
                    kb_id=document.kb_id,
                    filename=record.get("filename") or f"image_{index}",
                    minio_url=record.get("url") or record.get("minio_url"),
                    caption=record.get("caption") or "",
                    alt_text=record.get("alt_text") or "",
                )
            )
        document.image_count = len(unique_records)
        self.session.flush()
        return len(unique_records)

    def list_images(self, doc_id: str) -> list[dict]:
        statement = select(DocumentImage).where(DocumentImage.doc_id == doc_id).order_by(DocumentImage.created_at.asc())
        return [
            {
                "image_id": image.image_id,
                "filename": image.filename or "",
                "url": image.minio_url,
                "minio_url": image.minio_url,
                "caption": image.caption or "",
                "alt_text": image.alt_text or "",
            }
            for image in self.session.scalars(statement).all()
        ]

    def _refresh_kb_counts(self, kb_id: str) -> None:
        kb = self.session.get(KnowledgeBase, kb_id)
        if kb is None:
            return
        kb.doc_count = self.session.scalar(
            select(func.count()).select_from(Document).where(Document.kb_id == kb_id)
        ) or 0
        kb.chunk_count = self.session.scalar(
            select(func.coalesce(func.sum(Document.chunk_count), 0)).where(Document.kb_id == kb_id)
        ) or 0

    def to_dict(self, document: Document) -> dict:
        kb = self.session.get(KnowledgeBase, document.kb_id)
        return {
            "doc_id": document.doc_id,
            "kb_id": document.kb_id,
            "kb_name": kb.name if kb else document.kb_id,
            "filename": document.filename,
            "file_type": document.file_type or "",
            "file_path": document.file_path or "",
            "minio_url": document.minio_url or "",
            "parse_status": document.parse_status,
            "chunk_count": document.chunk_count,
            "image_count": document.image_count,
            "error_msg": document.error_msg or "",
            "created_at": document.created_at.isoformat(sep=" ", timespec="seconds") if document.created_at else "",
            "updated_at": document.updated_at.isoformat(sep=" ", timespec="seconds") if document.updated_at else "",
            "images": self.list_images(document.doc_id),
        }
