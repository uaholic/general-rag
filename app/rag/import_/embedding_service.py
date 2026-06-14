"""文档向量生成服务。"""
from __future__ import annotations

from typing import Any

from app.infra.llm.providers import llm_provider


class EmbeddingService:
    """封装 embedding 生成，节点层只关心输入输出。"""

    def embed_chunks(self, chunks: list[dict[str, Any]]) -> dict[str, list]:
        if not chunks:
            return {"dense": [], "sparse": []}

        texts = [chunk["content"] for chunk in chunks]
        # TODO: 练习点：这里会加载 BGE-M3，首次运行较慢；可以补批量大小、重试和耗时日志。
        return llm_provider.embed_documents(texts)

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
