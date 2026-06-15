"""回答生成服务。"""
from __future__ import annotations

import logging
from typing import Any

from langchain_core.messages import BaseMessage

from app.infra.llm.providers import llm_provider


logger = logging.getLogger(__name__)


class AnswerGenerationService:
    """根据检索结果生成回答。"""

    def generate(
        self,
        *,
        question: str,
        business_line: dict[str, Any],
        chunks: list[dict[str, Any]],
        model_name: str = "",
        use_llm: bool = False,
    ) -> str:
        fallback = business_line.get("fallback_message") or "抱歉，当前知识库中没有找到明确依据。"
        if not chunks:
            return fallback

        prompt = self.build_prompt(question=question, business_line=business_line, chunks=chunks)
        if use_llm:
            try:
                llm = llm_provider.chat(model_name or None)
                response = llm.invoke(prompt)
                if isinstance(response, BaseMessage):
                    return str(response.content).strip()
                return str(response).strip()
            except Exception as exc:
                logger.warning("LLM 回答生成失败，降级为抽取式回答: %s", exc)

        return self.extractive_answer(question=question, chunks=chunks)

    @staticmethod
    def extractive_answer(*, question: str, chunks: list[dict[str, Any]]) -> str:
        lines = ["根据已上传知识库资料，可以参考下面的信息："]
        for index, chunk in enumerate(chunks[:3], start=1):
            content = " ".join((chunk.get("content") or "").split())
            if len(content) > 260:
                content = content[:260].rstrip() + "..."
            title = chunk.get("title") or chunk.get("filename") or "引用资料"
            lines.append(f"\n[{index}] {title}\n{content}")
        lines.append("\n如果需要更精确的结论，可以继续追问具体概念、步骤或配置项。")
        _ = question
        return "\n".join(lines)

    @staticmethod
    def build_prompt(*, question: str, business_line: dict[str, Any], chunks: list[dict[str, Any]]) -> str:
        context = "\n\n".join(
            f"[{index + 1}] {chunk.get('content', '')}"
            for index, chunk in enumerate(chunks)
        )
        return f"""你是：{business_line.get("assistant_role") or "企业知识库助手"}

请只根据资料回答用户问题；资料没有依据时，不要编造。
回答要简洁、直接，并在适合的位置用 [1]、[2] 标注依据来源。

业务线额外要求：
{business_line.get("prompt_extra") or "无"}

资料：
{context}

用户问题：
{question}
"""


answer_generation_service = AnswerGenerationService()
