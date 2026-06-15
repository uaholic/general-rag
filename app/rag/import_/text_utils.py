"""文档文本处理工具。"""
from __future__ import annotations

from dataclasses import dataclass
import re


@dataclass(frozen=True)
class TextChunk:
    index: int
    content: str


class TextChunker:
    """把长文本切成有重叠的 chunk。"""

    def __init__(self, chunk_size: int = 800, chunk_overlap: int = 120) -> None:
        if chunk_size <= 0:
            raise ValueError("chunk_size 必须大于 0")
        if chunk_overlap < 0:
            raise ValueError("chunk_overlap 不能小于 0")
        if chunk_overlap >= chunk_size:
            raise ValueError("chunk_overlap 必须小于 chunk_size")
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap

    def split(self, text: str) -> list[TextChunk]:
        clean_text = self.normalize(text)
        if not clean_text:
            return []

        chunks: list[TextChunk] = []
        start = 0
        while start < len(clean_text):
            end = min(start + self.chunk_size, len(clean_text))
            content = clean_text[start:end].strip()
            if content:
                chunks.append(TextChunk(index=len(chunks), content=content))
            if end >= len(clean_text):
                break
            next_start = end - self.chunk_overlap
            start = next_start if next_start > start else end
        return chunks

    @staticmethod
    def normalize(text: str) -> str:
        """收敛空白字符，避免 chunk 里充满无意义换行。"""
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        text = re.sub(r"\n{3,}", "\n\n", text)
        text = re.sub(r"[ \t]+", " ", text)
        return text.strip()
