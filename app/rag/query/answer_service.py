"""回答生成服务。"""
from __future__ import annotations

from typing import Any

from langchain_core.messages import BaseMessage

from app.infra.llm.providers import llm_provider


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
        if not use_llm:
            # 练习阶段先返回可读的检索摘要；打开 use_llm 后再真正调模型。
            joined = "\n".join(f"{index + 1}. {chunk.get('content', '')[:160]}" for index, chunk in enumerate(chunks[:3]))
            return f"已检索到相关资料，后续请在 AnswerGenerationService.generate 中接入 LLM 生成自然语言回答。\n\n{joined}"

        llm = llm_provider.chat(model_name or None)
        response = llm.invoke(prompt)
        if isinstance(response, BaseMessage):
            return str(response.content)
        return str(response)

    @staticmethod
    def build_prompt(*, question: str, business_line: dict[str, Any], chunks: list[dict[str, Any]]) -> str:
        context = "\n\n".join(
            f"[{index + 1}] {chunk.get('content', '')}"
            for index, chunk in enumerate(chunks)
        )
        return f"""你是：{business_line.get("assistant_role") or "企业知识库助手"}

请只根据资料回答用户问题；资料没有依据时，不要编造。

业务线额外要求：
{business_line.get("prompt_extra") or "无"}

资料：
{context}

用户问题：
{question}
"""


answer_generation_service = AnswerGenerationService()
