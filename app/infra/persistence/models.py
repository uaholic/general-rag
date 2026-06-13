"""MySQL ORM 模型。"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, Index, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.infra.persistence.mysql import Base


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


class SystemConfig(TimestampMixin, Base):
    __tablename__ = "system_config"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    company_name: Mapped[str] = mapped_column(String(255), nullable=False)
    industry: Mapped[str | None] = mapped_column(String(255))
    company_description: Mapped[str | None] = mapped_column(Text)
    business_scope: Mapped[str | None] = mapped_column(Text)
    answer_tone: Mapped[str | None] = mapped_column(String(255))
    welcome_message: Mapped[str | None] = mapped_column(Text)
    fallback_message: Mapped[str | None] = mapped_column(Text)
    disclaimer: Mapped[str | None] = mapped_column(Text)


class BusinessLineConfig(TimestampMixin, Base):
    __tablename__ = "business_line_config"
    __table_args__ = (Index("idx_business_line_enabled", "enabled"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    business_line_name: Mapped[str] = mapped_column(String(255), nullable=False)
    business_line_description: Mapped[str | None] = mapped_column(Text)
    scenario: Mapped[str | None] = mapped_column(Text)
    target_user: Mapped[str | None] = mapped_column(Text)
    assistant_role: Mapped[str | None] = mapped_column(Text)
    welcome_message: Mapped[str | None] = mapped_column(Text)
    fallback_message: Mapped[str | None] = mapped_column(Text)
    prompt_extra: Mapped[str | None] = mapped_column(Text)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class KnowledgeBase(TimestampMixin, Base):
    __tablename__ = "knowledge_base"
    __table_args__ = (Index("idx_knowledge_base_enabled", "enabled"),)

    kb_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    doc_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    chunk_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class BusinessLineKnowledgeBase(Base):
    __tablename__ = "business_line_knowledge_base"
    __table_args__ = (
        UniqueConstraint("business_line_id", "kb_id", name="uk_business_line_kb"),
        Index("idx_blk_business_line", "business_line_id"),
        Index("idx_blk_kb", "kb_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    business_line_id: Mapped[str] = mapped_column(String(64), nullable=False)
    kb_id: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class Document(TimestampMixin, Base):
    __tablename__ = "document"
    __table_args__ = (
        Index("idx_document_kb_id", "kb_id"),
        Index("idx_document_parse_status", "parse_status"),
    )

    doc_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    kb_id: Mapped[str] = mapped_column(String(64), nullable=False)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    file_type: Mapped[str | None] = mapped_column(String(32))
    file_path: Mapped[str | None] = mapped_column(String(1024))
    minio_url: Mapped[str | None] = mapped_column(String(1024))
    parse_status: Mapped[str] = mapped_column(String(32), default="pending", nullable=False)
    chunk_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    image_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error_msg: Mapped[str | None] = mapped_column(Text)


class DocumentImage(TimestampMixin, Base):
    __tablename__ = "document_image"
    __table_args__ = (
        Index("idx_document_image_doc_id", "doc_id"),
        Index("idx_document_image_kb_id", "kb_id"),
    )

    image_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    doc_id: Mapped[str] = mapped_column(String(64), nullable=False)
    kb_id: Mapped[str] = mapped_column(String(64), nullable=False)
    filename: Mapped[str | None] = mapped_column(String(255))
    minio_url: Mapped[str] = mapped_column(String(1024), nullable=False)
    caption: Mapped[str | None] = mapped_column(Text)
    alt_text: Mapped[str | None] = mapped_column(Text)


class ModelConfig(TimestampMixin, Base):
    __tablename__ = "model_config"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    llm_model_name: Mapped[str | None] = mapped_column(String(255))
    embedding_model_name: Mapped[str | None] = mapped_column(String(255))
    rerank_model_name: Mapped[str | None] = mapped_column(String(255))
    image_model_name: Mapped[str | None] = mapped_column(String(255))
    top_k: Mapped[int] = mapped_column(Integer, default=5, nullable=False)
    use_rerank: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
