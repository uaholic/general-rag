"""回答生成服务。"""
from __future__ import annotations

import logging
import re
from typing import Any

from langchain_core.messages import BaseMessage

from app.infra.llm.providers import llm_provider


logger = logging.getLogger(__name__)


class AnswerGenerationService:
    """根据检索结果生成回答。"""

    _IMAGE_MARKDOWN_RE = re.compile(r"!\[([^\]]*)]\((https?://[^)\s]+)\)")
    _IMAGE_URL_RE = re.compile(r"https?://[^\s)\]]+\.(?:png|jpe?g|webp|gif)(?:\?[^\s)\]]*)?", re.I)
    _HTTP_URL_RE = re.compile(r"https?://[^\s)\]]+")
    _IMAGE_MARKER_PREFIXES = ("[[IMAGE_", "【IMAGE_")

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

        prompt, images = self.build_prompt_payload(question=question, business_line=business_line, chunks=chunks)
        if use_llm:
            try:
                llm = llm_provider.chat(model_name or None)
                response = llm.invoke(prompt)
                if isinstance(response, BaseMessage):
                    return self.replace_image_markers(str(response.content).strip(), images)
                return self.replace_image_markers(str(response).strip(), images)
            except Exception as exc:
                logger.warning("LLM 回答生成失败，降级为抽取式回答: %s", exc)

        return self.extractive_answer(question=question, chunks=chunks)

    def stream_generate(
        self,
        *,
        question: str,
        business_line: dict[str, Any],
        chunks: list[dict[str, Any]],
        model_name: str = "",
        use_llm: bool = True,
    ):
        """流式生成回答，yield 文本片段。"""
        fallback = business_line.get("fallback_message") or "抱歉，当前知识库中没有找到明确依据。"
        if not chunks:
            yield fallback
            return

        prompt, images = self.build_prompt_payload(question=question, business_line=business_line, chunks=chunks)
        if use_llm:
            try:
                llm = llm_provider.chat(model_name or None)
                buffer = ""
                for chunk in llm.stream(prompt):
                    text = self._message_to_text(chunk)
                    if not text:
                        continue
                    buffer += text
                    safe_text, buffer = self._pop_safe_stream_text(buffer)
                    if safe_text:
                        yield self.replace_image_markers(safe_text, images)
                if buffer:
                    yield self.replace_image_markers(buffer, images)
                return
            except Exception as exc:
                logger.warning("LLM 流式回答生成失败，降级为抽取式回答: %s", exc)

        yield self.extractive_answer(question=question, chunks=chunks)

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

    @classmethod
    def build_prompt(cls, *, question: str, business_line: dict[str, Any], chunks: list[dict[str, Any]]) -> str:
        prompt, _ = cls.build_prompt_payload(question=question, business_line=business_line, chunks=chunks)
        return prompt

    @classmethod
    def build_prompt_payload(
        cls,
        *,
        question: str,
        business_line: dict[str, Any],
        chunks: list[dict[str, Any]],
    ) -> tuple[str, list[dict[str, str]]]:
        images = cls._build_image_registry(chunks)
        url_to_marker = {item["url"]: item["marker"] for item in images}
        context = "\n\n".join(
            cls._format_chunk(index=index + 1, chunk=chunk, url_to_marker=url_to_marker)
            for index, chunk in enumerate(chunks)
        )
        image_instructions = "\n".join(
            f"- {item['marker']}：{item['caption']}"
            for item in images
        ) or "无"
        prompt = f"""你是：{business_line.get("assistant_role") or "企业知识库助手"}

请只根据资料回答用户问题；资料没有依据时，不要编造。
回答要求：
1. 使用 Markdown 输出，结构清晰。
2. 如果涉及公式，用 LaTeX：行内公式用 \\(...\\)，独立公式用 $$...$$。
3. 在适合的位置用 [1]、[2] 标注依据来源。
4. 如果资料图片对回答有帮助，只能在相关段落附近单独输出图片标记，例如：[[IMAGE_1]]。
5. 严禁输出、改写、猜测任何 http/https 图片 URL；程序会把图片标记替换成真实地址。
6. 不要输出与资料无关的图片。

可用图片标记：
{image_instructions}

业务线额外要求：
{business_line.get("prompt_extra") or "无"}

资料：
{context}

用户问题：
{question}
"""
        return prompt, images

    @classmethod
    def _format_chunk(cls, *, index: int, chunk: dict[str, Any], url_to_marker: dict[str, str]) -> str:
        image_urls = chunk.get("image_urls") or []
        subjects = chunk.get("subject_names") or []
        content = cls._replace_image_urls_with_markers(chunk.get("content", ""), url_to_marker)
        images = "\n".join(
            f"- {url_to_marker[url]}"
            for url in image_urls
            if url in url_to_marker
        )
        return (
            f"[{index}] 标题：{chunk.get('title') or chunk.get('filename') or '引用资料'}\n"
            f"主体：{', '.join(subjects) or '无'}\n"
            f"图片标记：\n{images or '无'}\n"
            f"内容：\n{content}"
        )

    @staticmethod
    def _build_image_registry(chunks: list[dict[str, Any]]) -> list[dict[str, str]]:
        images: list[dict[str, str]] = []
        seen: set[str] = set()

        def add_image(url: str, caption: str) -> None:
            url = str(url or "").strip()
            if not url or url in seen:
                return
            seen.add(url)
            images.append(
                {
                    "marker": f"[[IMAGE_{len(images) + 1}]]",
                    "url": url,
                    "caption": caption or "知识库图片",
                }
            )

        for chunk in chunks:
            default_caption = str(chunk.get("title") or chunk.get("filename") or "知识库图片")
            for url in chunk.get("image_urls") or []:
                add_image(url, default_caption)
            content = str(chunk.get("content") or "")
            for match in AnswerGenerationService._IMAGE_MARKDOWN_RE.finditer(content):
                add_image(match.group(2), match.group(1).strip() or default_caption)
            for match in AnswerGenerationService._IMAGE_URL_RE.finditer(content):
                add_image(match.group(0), default_caption)
        return images

    @classmethod
    def _replace_image_urls_with_markers(cls, content: str, url_to_marker: dict[str, str]) -> str:
        text = str(content or "")

        def replace_image(match: re.Match) -> str:
            alt = match.group(1).strip() or "资料图片"
            url = match.group(2)
            marker = url_to_marker.get(url)
            return f"图片：{alt} {marker}" if marker else f"图片：{alt}"

        text = cls._IMAGE_MARKDOWN_RE.sub(replace_image, text)
        for url, marker in sorted(url_to_marker.items(), key=lambda item: len(item[0]), reverse=True):
            text = text.replace(url, marker)
        text = cls._HTTP_URL_RE.sub("[URL已隐藏]", text)
        return text

    @staticmethod
    def replace_image_markers(text: str, images: list[dict[str, str]]) -> str:
        result = str(text or "")
        for item in images:
            marker = item["marker"]
            marker_name = marker.strip("[]")
            alt = item.get("caption") or "知识库图片"
            alt = alt.replace("[", "(").replace("]", ")").replace("\n", " ")
            markdown = f"![{alt}]({item['url']})"
            candidates = (marker, f"【{marker_name}】", marker_name)
            for candidate in candidates:
                result = re.sub(
                    rf"!\[([^\]]*)]\(\s*{re.escape(candidate)}\s*\)",
                    lambda match: f"![{(match.group(1).strip() or alt).replace('[', '(').replace(']', ')')}]({item['url']})",
                    result,
                )
            for candidate in candidates:
                result = result.replace(candidate, markdown)
        return result

    @classmethod
    def _pop_safe_stream_text(cls, buffer: str) -> tuple[str, str]:
        if len(buffer) <= 96:
            return "", buffer
        safe_len = len(buffer) - 96
        window_start = max(0, safe_len - 32)
        for prefix in cls._IMAGE_MARKER_PREFIXES:
            index = buffer.rfind(prefix, window_start)
            if index < 0:
                continue
            end_token = "]]" if prefix == "[[IMAGE_" else "】"
            end_index = buffer.find(end_token, index + len(prefix))
            if end_index < 0 or end_index + len(end_token) > safe_len:
                safe_len = min(safe_len, index)
        return buffer[:safe_len], buffer[safe_len:]

    @staticmethod
    def _message_to_text(response: Any) -> str:
        if isinstance(response, BaseMessage):
            content = response.content
        else:
            content = getattr(response, "content", response)
        if isinstance(content, list):
            parts = []
            for item in content:
                if isinstance(item, dict):
                    parts.append(str(item.get("text") or item.get("content") or ""))
                else:
                    parts.append(str(item))
            return "".join(parts)
        return str(content or "")


answer_generation_service = AnswerGenerationService()
