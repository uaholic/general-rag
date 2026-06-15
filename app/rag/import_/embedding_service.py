"""文档向量生成服务。"""
from __future__ import annotations

import time
from typing import Any

from app.infra.llm.providers import llm_provider
from app.rag.import_.config import EMBEDDING_BATCH_SIZE


class EmbeddingService:
    """封装 embedding 生成，节点层只关心输入输出。"""

    def embed_chunks(self, chunks: list[dict[str, Any]]) -> dict[str, list]:
        if not chunks:
            return {"dense": [], "sparse": []}

        texts = [chunk["content"] for chunk in chunks]
        dense: list = []
        sparse: list = []
        started_at = time.perf_counter()
        batch_size = max(1, EMBEDDING_BATCH_SIZE)
        for start in range(0, len(texts), batch_size):
            batch = texts[start:start + batch_size]
            result = llm_provider.embed_documents(batch)
            dense.extend(result.get("dense") or [])
            sparse.extend(result.get("sparse") or [])
        _ = started_at
        return {"dense": dense, "sparse": sparse}

    def attach_embeddings(
        self,
        chunks: list[dict[str, Any]],
        embeddings: dict[str, list],
    ) -> list[dict[str, Any]]:
        """把 dense/sparse 向量合并回 chunk payload，准备写入 Milvus。"""
        dense_list = embeddings.get("dense") or []
        sparse_list = embeddings.get("sparse") or []
        records: list[dict[str, Any]] = []
        for index, chunk in enumerate(chunks):
            record = dict(chunk)
            record["dense_vector"] = dense_list[index] if index < len(dense_list) else []
            record["sparse_vector"] = sparse_list[index] if index < len(sparse_list) else {}
            records.append(record)
        return records


embedding_service = EmbeddingService()
