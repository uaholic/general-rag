"""查询检索服务。"""
from __future__ import annotations

from pathlib import Path
import re
from typing import Any

from sqlalchemy import select

from app.infra.llm.providers import llm_provider
from app.infra.persistence.models import Document
from app.infra.persistence.mysql import session_scope
from app.infra.vectorstore.milvus_gateway import milvus_gateway
from app.rag.import_.pdf_parser_service import pdf_parser_service
from app.rag.import_.text_utils import TextChunker
from app.shared.utils.escape_milvus_string_utils import escape_milvus_string


class QueryRetrievalService:
    """负责把用户问题转换为检索结果。

    当前默认走本地文档轻量检索，保证没有 Milvus 时也能练习完整链路。
    打开 use_milvus 后，会走 BGE-M3 + Milvus 混合检索骨架。
    """

    def rewrite_query(self, question: str) -> str:
        # TODO: 练习点：接 LLM 做问题改写，例如补全上下文、统一主体名称。
        return question.strip()

    def search(
        self,
        *,
        query: str,
        kb_ids: list[str],
        top_k: int = 5,
        use_milvus: bool = False,
    ) -> list[dict[str, Any]]:
        if not kb_ids:
            return []
        if use_milvus:
            return self.search_milvus(query=query, kb_ids=kb_ids, top_k=top_k)
        return self.search_local_documents(query=query, kb_ids=kb_ids, top_k=top_k)

    def search_local_documents(self, *, query: str, kb_ids: list[str], top_k: int = 5) -> list[dict[str, Any]]:
        """没有向量库时的练习版检索：读取 success 文档，按关键词做粗略打分。"""
        keywords = self._keywords(query)
        if not keywords:
            return []

        candidates: list[dict[str, Any]] = []
        with session_scope() as session:
            statement = (
                select(Document)
                .where(Document.kb_id.in_(kb_ids))
                .where(Document.parse_status == "success")
            )
            for document in session.scalars(statement).all():
                path = self._local_text_path(document)
                if path is None:
                    continue
                if not path.exists():
                    continue
                text = path.read_text(encoding="utf-8", errors="ignore")
                chunks = TextChunker(chunk_size=800, chunk_overlap=120).split(text)
                for chunk in chunks:
                    score = self._score(chunk.content, keywords)
                    if score <= 0:
                        continue
                    candidates.append(
                        {
                            "chunk_id": f"{document.doc_id}_{chunk.index}",
                            "doc_id": document.doc_id,
                            "kb_id": document.kb_id,
                            "filename": document.filename,
                            "title": document.filename,
                            "content": chunk.content,
                            "score": score,
                            "image_urls": [],
                            "subject_names": [],
                        }
                    )

        candidates.sort(key=lambda item: item["score"], reverse=True)
        return candidates[:top_k]

    def search_milvus(self, *, query: str, kb_ids: list[str], top_k: int = 5) -> list[dict[str, Any]]:
        """Milvus 混合检索骨架。"""
        embeddings = llm_provider.embed_documents([query])
        dense_vector = embeddings["dense"][0]
        sparse_vector = embeddings["sparse"][0]
        expr = self.build_kb_filter_expr(kb_ids)
        requests = milvus_gateway.create_requests(
            dense_vector=dense_vector,
            sparse_vector=sparse_vector,
            expr=expr,
            limit=top_k,
        )
        result = milvus_gateway.hybrid_search(
            collection_name=milvus_gateway.chunk_collection_name,
            reqs=requests,
            limit=top_k,
        )
        if not result:
            return []
        return [self._normalize_milvus_hit(hit) for hit in result[0]]

    def rerank(self, *, query: str, chunks: list[dict[str, Any]], top_k: int = 5, use_rerank: bool = False) -> list[dict[str, Any]]:
        if not use_rerank or not chunks:
            return chunks[:top_k]

        # TODO: 练习点：调用 llm_provider.reranker_model().compute_score，
        # 按 [query, chunk["content"]] 对打分后重排。
        _ = query
        return chunks[:top_k]

    def build_references(self, chunks: list[dict[str, Any]]) -> list[dict[str, Any]]:
        references: list[dict[str, Any]] = []
        for index, chunk in enumerate(chunks, start=1):
            references.append(
                {
                    "index": index,
                    "doc_id": chunk.get("doc_id", ""),
                    "chunk_id": chunk.get("chunk_id", ""),
                    "title": chunk.get("title") or chunk.get("filename") or "引用文档",
                    "text": (chunk.get("content") or "")[:300],
                    "score": chunk.get("score"),
                }
            )
        return references

    def collect_images(self, chunks: list[dict[str, Any]]) -> list[dict[str, Any]]:
        images: list[dict[str, Any]] = []
        for chunk in chunks:
            for url in chunk.get("image_urls") or []:
                images.append({"url": url, "caption": chunk.get("title") or chunk.get("filename") or ""})
        return images

    @staticmethod
    def build_kb_filter_expr(kb_ids: list[str]) -> str:
        escaped_ids = [f'"{escape_milvus_string(kb_id)}"' for kb_id in kb_ids]
        return f"kb_id in [{', '.join(escaped_ids)}]"

    @staticmethod
    def _normalize_milvus_hit(hit: Any) -> dict[str, Any]:
        if isinstance(hit, dict):
            entity = hit.get("entity", {}) or {}
            distance = hit.get("distance")
        else:
            entity = getattr(hit, "entity", None) or {}
            distance = getattr(hit, "distance", None)
        return {
            **dict(entity),
            "score": distance,
        }

    @staticmethod
    def _keywords(query: str) -> list[str]:
        return [item for item in re.split(r"\W+", query.lower()) if len(item) >= 2]

    @staticmethod
    def _local_text_path(document: Document) -> Path | None:
        file_type = (document.file_type or "").lower()
        if file_type in {"txt", "md", "markdown"}:
            return Path(document.file_path or "")
        if file_type == "pdf":
            return pdf_parser_service.find_latest_markdown(document.doc_id)
        return None

    @staticmethod
    def _score(text: str, keywords: list[str]) -> float:
        lowered = text.lower()
        return float(sum(lowered.count(keyword) for keyword in keywords))


query_retrieval_service = QueryRetrievalService()
