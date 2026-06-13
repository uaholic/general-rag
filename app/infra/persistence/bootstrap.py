"""数据库初始化与演示数据。"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.infra.persistence.admin_repositories import (
    BusinessLineRepository,
    KnowledgeBaseRepository,
    ModelConfigRepository,
    SystemConfigRepository,
)
from app.infra.persistence.models import KnowledgeBase
from app.infra.persistence.mysql import Base, get_engine, session_scope


def init_database(seed: bool = True) -> None:
    """创建基础表，并在空库时写入原型演示数据。"""
    Base.metadata.create_all(bind=get_engine())
    if seed:
        with session_scope() as session:
            seed_demo_data(session)


def seed_demo_data(session: Session) -> None:
    SystemConfigRepository(session).get_default()
    ModelConfigRepository(session).get_default()

    kb_repo = KnowledgeBaseRepository(session)
    if not session.scalar(select(KnowledgeBase.kb_id).limit(1)):
        for item in (
            {
                "kb_id": "kb_course",
                "name": "大模型课程库",
                "description": "RAG、LangChain、Embedding 学习资料",
                "enabled": True,
            },
            {
                "kb_id": "kb_milvus",
                "name": "Milvus资料库",
                "description": "向量数据库实践材料",
                "enabled": True,
            },
            {
                "kb_id": "kb_product",
                "name": "产品资料库",
                "description": "产品能力、案例、交付流程",
                "enabled": True,
            },
            {
                "kb_id": "kb_pricing",
                "name": "价格政策库",
                "description": "套餐、报价、合同条款",
                "enabled": False,
            },
            {
                "kb_id": "kb_embedding",
                "name": "Embedding 资料库",
                "description": "BGE-M3、向量化、稀疏向量",
                "enabled": True,
            },
            {
                "kb_id": "kb_support",
                "name": "售后知识库",
                "description": "使用说明、故障排查、操作指南",
                "enabled": True,
            },
        ):
            kb_repo.save(item)

    line_repo = BusinessLineRepository(session)
    if not line_repo.get("business_line_course"):
        line_repo.save(
            {
                "business_line_id": "business_line_course",
                "business_line_name": "大模型学习助手",
                "business_line_description": "用于回答大模型、RAG、Agent、LangChain、Milvus 等学习资料相关问题。",
                "scenario": "课程答疑、项目文档问答、技术知识库问答",
                "target_user": "正在学习 AI 应用开发的学生和开发者",
                "assistant_role": "你是一个耐心、专业、能用通俗语言解释复杂技术概念的 AI 学习助手。",
                "welcome_message": "你好，我是课程知识库助手，可以帮你解答大模型学习问题。",
                "fallback_message": "抱歉，当前业务线绑定的知识库中没有找到明确依据。",
                "prompt_extra": "",
                "enabled": True,
                "kb_ids": ["kb_course", "kb_milvus", "kb_embedding"],
            }
        )
    if not line_repo.get("business_line_sales"):
        line_repo.save(
            {
                "business_line_id": "business_line_sales",
                "business_line_name": "售前咨询助手",
                "business_line_description": "用于官网访客咨询、产品介绍和套餐政策问答。",
                "scenario": "官网访客咨询、产品介绍",
                "target_user": "官网访客和潜在客户",
                "assistant_role": "你是一个清晰、专业的售前咨询助手。",
                "welcome_message": "你好，我是售前咨询助手，可以介绍产品能力、案例和套餐政策。",
                "fallback_message": "抱歉，当前售前知识库中没有找到明确依据。",
                "prompt_extra": "",
                "enabled": True,
                "kb_ids": ["kb_product", "kb_pricing"],
            }
        )
    if not line_repo.get("business_line_support"):
        line_repo.save(
            {
                "business_line_id": "business_line_support",
                "business_line_name": "售后服务助手",
                "business_line_description": "用于使用说明和故障排查。",
                "scenario": "使用问题、故障排查",
                "target_user": "已购买客户和内部支持人员",
                "assistant_role": "你是一个耐心的售后服务助手。",
                "welcome_message": "你好，我是售后服务助手，可以帮你查询使用说明和故障排查资料。",
                "fallback_message": "抱歉，售后知识库中没有找到明确依据。",
                "prompt_extra": "",
                "enabled": False,
                "kb_ids": ["kb_support"],
            }
        )

    kb_repo.unbind_disabled()
