"""查询运行时配置读取服务。"""
from __future__ import annotations

from typing import Any

from app.infra.persistence.admin_repositories import (
    BusinessLineRepository,
    ModelConfigRepository,
    SystemConfigRepository,
)
from app.infra.persistence.mysql import session_scope


class QueryRuntimeService:
    """读取企业、模型、业务线和绑定知识库配置。"""

    def load_runtime(self, business_line_id: str) -> dict[str, Any]:
        with session_scope() as session:
            company_repo = SystemConfigRepository(session)
            model_repo = ModelConfigRepository(session)
            line_repo = BusinessLineRepository(session)

            company = company_repo.to_dict(company_repo.get_default())
            model = model_repo.to_dict(model_repo.get_default())
            business_line = line_repo.get_dict(business_line_id)
            if business_line is None:
                raise ValueError("业务线不存在")
            if not business_line["enabled"]:
                raise ValueError("业务线已停用")

            kb_ids = [kb["kb_id"] for kb in business_line.get("knowledge_bases", []) if kb.get("enabled")]
            return {
                "company_config": company,
                "model_config": model,
                "business_line": business_line,
                "kb_ids": kb_ids,
                "top_k": model.get("top_k") or 5,
                "use_rerank": bool(model.get("use_rerank")),
            }


query_runtime_service = QueryRuntimeService()
