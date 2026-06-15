"""查询检索服务。"""
from __future__ import annotations

import json
from pathlib import Path
import re
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.infra.llm.providers import llm_provider
from app.infra.persistence.history_repository import history_repository
from app.infra.persistence.admin_repositories import DocumentRepository
from app.infra.persistence.models import Document
from app.infra.persistence.mysql import session_scope
from app.infra.vectorstore.milvus_gateway import milvus_gateway
from app.rag.import_.pdf_parser_service import pdf_parser_service
from app.rag.import_.text_utils import TextChunker
from app.shared.utils.escape_milvus_string_utils import escape_milvus_string


class QueryRetrievalService:
    """负责把用户问题转换为检索结果。"""

    def rewrite_query(
        self,
        *,
        question: str,
        session_id: str = "",
        business_line: dict[str, Any] | None = None,
        model_name: str = "",
    ) -> dict[str, Any]:
        """结合历史把用户问题改写成独立检索问题，并抽取主体词。"""
        normalized_question = " ".join(question.strip().split())
        history = self._recent_history(session_id=session_id, current_question=normalized_question)
        prompt = self._rewrite_prompt(
            question=normalized_question,
            history=history,
            business_line=business_line or {},
        )
        try:
            llm = llm_provider.chat(model_name or "qwen-flash", json_mode=True)
            response = llm.invoke(prompt)
            data = self._json_from_response(response)
            rewritten_query = " ".join(str(data.get("rewritten_query") or normalized_question).split())
            subject_names = self._normalize_subjects(data.get("subject_names") or [])
            return {
                "rewritten_query": rewritten_query or normalized_question,
                "query_subject_names": subject_names,
            }
        except Exception:
            return {
                "rewritten_query": normalized_question,
                "query_subject_names": self._fallback_subjects(normalized_question),
            }

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
            try:
                chunks = self.search_milvus(query=query, kb_ids=kb_ids, top_k=top_k)
                if chunks:
                    return chunks
            except Exception:
                pass
        return self.search_local_documents(query=query, kb_ids=kb_ids, top_k=top_k)

    def search_local_documents(self, *, query: str, kb_ids: list[str], top_k: int = 5) -> list[dict[str, Any]]:
        """没有向量库时的本地检索：读取 success 文档，按关键词做粗略打分。"""
        keywords = self._keywords(query)
        if not keywords:
            return []

        candidates: list[dict[str, Any]] = []
        with session_scope() as session:
            repo = DocumentRepository(session)
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
                image_lookup = self._document_image_lookup(repo, document.doc_id)
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
                            "image_urls": self._image_urls_for_chunk(chunk.content, image_lookup),
                            "subject_names": self._fallback_subjects(chunk.content),
                        }
                    )

        candidates.sort(key=lambda item: item["score"], reverse=True)
        return candidates[:top_k]

    def search_milvus(self, *, query: str, kb_ids: list[str], top_k: int = 5) -> list[dict[str, Any]]:
        """Milvus 混合检索骨架。"""
        collection_name = milvus_gateway.chunk_collection_name
        if not milvus_gateway.client.has_collection(collection_name):
            return []
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
            collection_name=collection_name,
            reqs=requests,
            limit=top_k,
        )
        if not result:
            return []
        return [self._normalize_milvus_hit(hit) for hit in result[0]]

    def rerank(self, *, query: str, chunks: list[dict[str, Any]], top_k: int = 5, use_rerank: bool = False) -> list[dict[str, Any]]:
        if not use_rerank or not chunks:
            return chunks[:top_k]

        try:
            reranker = llm_provider.reranker_model()
            pairs = [[query, chunk.get("content", "")] for chunk in chunks]
            scores = reranker.compute_score(pairs)
            if not isinstance(scores, list):
                scores = [float(scores)]
            scored_chunks = []
            for index, chunk in enumerate(chunks):
                item = dict(chunk)
                if index < len(scores):
                    item["rerank_score"] = float(scores[index])
                    item["score"] = float(scores[index])
                scored_chunks.append(item)
            scored_chunks.sort(key=lambda item: item.get("rerank_score", item.get("score", 0)), reverse=True)
            return scored_chunks[:top_k]
        except Exception:
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
                    "subject_names": chunk.get("subject_names") or [],
                    "image_urls": chunk.get("image_urls") or [],
                }
            )
        return references

    def collect_images(self, chunks: list[dict[str, Any]]) -> list[dict[str, Any]]:
        images: list[dict[str, Any]] = []
        seen: set[str] = set()
        for chunk in chunks:
            for url in chunk.get("image_urls") or []:
                if not url or url in seen:
                    continue
                seen.add(url)
                images.append({"url": url, "caption": chunk.get("title") or chunk.get("filename") or ""})
        return images

    @staticmethod
    def _recent_history(*, session_id: str, current_question: str, limit: int = 8) -> list[dict[str, str]]:
        if not session_id:
            return []
        try:
            messages = history_repository.list_recent(session_id=session_id, limit=limit)
        except Exception:
            return []
        result: list[dict[str, str]] = []
        for item in messages:
            role = str(item.get("role") or "")
            content = str(item.get("content") or "").strip()
            if not role or not content:
                continue
            if role == "user" and content == current_question:
                continue
            result.append({"role": role, "content": content[:500]})
        return result[-limit:]

    @staticmethod
    def _rewrite_prompt(*, question: str, history: list[dict[str, str]], business_line: dict[str, Any]) -> str:
        return f"""你是企业 RAG 检索前的问题改写器。
请结合历史对话，把用户当前问题改写成一个可独立检索的问题；即使没有历史，也要规范化表达。
同时抽取 1 到 6 个本轮关联主体词，主体词可以是技术名词、产品名、业务名词、概念名。

只返回 JSON，格式：
{{"rewritten_query":"...","subject_names":["..."]}}

业务线：{business_line.get("business_line_name") or business_line.get("scenario") or "默认业务线"}
历史对话：
{json.dumps(history, ensure_ascii=False)}

当前问题：
{question}
"""

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
            "subject_names": QueryRetrievalService._parse_json_list(entity.get("subject_names")),
            "image_urls": QueryRetrievalService._parse_json_list(entity.get("image_urls")),
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
    def _document_image_lookup(repo: DocumentRepository, doc_id: str) -> dict[str, str]:
        lookup: dict[str, str] = {}
        for image in repo.list_images(doc_id):
            url = image.get("url") or image.get("minio_url") or ""
            filename = image.get("filename") or ""
            if not url:
                continue
            lookup[url] = url
            if filename:
                lookup[filename] = url
        return lookup

    @staticmethod
    def _image_urls_for_chunk(text: str, lookup: dict[str, str]) -> list[str]:
        urls: list[str] = []
        for marker, url in lookup.items():
            if marker and marker in text and url not in urls:
                urls.append(url)
        return urls

    @staticmethod
    def _parse_json_list(value: Any) -> list:
        if isinstance(value, list):
            return value
        if not value:
            return []
        if isinstance(value, str):
            try:
                parsed = json.loads(value)
                return parsed if isinstance(parsed, list) else []
            except json.JSONDecodeError:
                return [item.strip() for item in value.split(",") if item.strip()]
        return []

    @staticmethod
    def _json_from_response(response: Any) -> dict[str, Any]:
        content = getattr(response, "content", response)
        if isinstance(content, list):
            text = " ".join(str(item.get("text") if isinstance(item, dict) else item) for item in content)
        else:
            text = str(content or "")
        text = text.strip()
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
            if len(subjects) >= 6:
                break
        return subjects

    @staticmethod
    def _fallback_subjects(text: str) -> list[str]:
        tokens = re.findall(
            r"[A-Za-z][A-Za-z0-9_+.#/-]{1,30}|[\u4e00-\u9fa5]{2,12}(?:模型|知识库|向量|检索|算法|流程|框架|数据库|技术|服务|系统|业务|图片|文档|课程)",
            text or "",
        )
        subjects: list[str] = []
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
        for token in tokens:
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
            if token not in subjects:
                subjects.append(token)
            if len(subjects) >= 6:
                break
        return subjects

    @staticmethod
    def _score(text: str, keywords: list[str]) -> float:
        lowered = text.lower()
        return float(sum(lowered.count(keyword) for keyword in keywords))


query_retrieval_service = QueryRetrievalService()
