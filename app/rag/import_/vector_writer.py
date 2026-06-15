"""文档向量写入服务。"""
from __future__ import annotations

from datetime import datetime
import json
from typing import Any

from pymilvus import DataType, MilvusClient

from app.infra.vectorstore.milvus_gateway import milvus_gateway
from app.shared.utils.escape_milvus_string_utils import escape_milvus_string


class VectorWriteService:
    """封装 Milvus 写入与删除。"""

    def delete_document_chunks(self, doc_id: str) -> int:
        """删除某个文档旧 chunk。"""
        if not doc_id:
            return 0
        if not milvus_gateway.client.has_collection(milvus_gateway.chunk_collection_name):
            return 0
        result = milvus_gateway.client.delete(
            collection_name=milvus_gateway.chunk_collection_name,
            filter=f'doc_id == "{escape_milvus_string(doc_id)}"',
        )
        if isinstance(result, dict):
            return int(result.get("delete_count") or result.get("delete_cnt") or 0)
        return 0

    def upsert_chunks(self, records: list[dict[str, Any]]) -> int:
        """写入 chunk 向量。"""
        rows = [self._to_milvus_row(record) for record in records if record.get("dense_vector")]
        if not rows:
            return 0
        collection_name = milvus_gateway.chunk_collection_name
        self.ensure_chunk_collection(milvus_gateway.client, collection_name, len(rows[0]["dense_vector"]))
        milvus_gateway.client.upsert(collection_name=collection_name, data=rows)
        return len(rows)

    def ensure_chunk_collection(self, client: MilvusClient, collection_name: str, dense_dim: int) -> None:
        if client.has_collection(collection_name):
            return

        schema = MilvusClient.create_schema(auto_id=False, enable_dynamic_field=False)
        schema.add_field("chunk_id", DataType.VARCHAR, is_primary=True, max_length=128)
        schema.add_field("kb_id", DataType.VARCHAR, max_length=128)
        schema.add_field("doc_id", DataType.VARCHAR, max_length=128)
        schema.add_field("filename", DataType.VARCHAR, max_length=512)
        schema.add_field("title", DataType.VARCHAR, max_length=512)
        schema.add_field("title_path", DataType.VARCHAR, max_length=1024)
        schema.add_field("content", DataType.VARCHAR, max_length=8192)
        schema.add_field("chunk_index", DataType.INT64)
        schema.add_field("subject_names", DataType.VARCHAR, max_length=2048)
        schema.add_field("image_urls", DataType.VARCHAR, max_length=4096)
        schema.add_field("created_at", DataType.VARCHAR, max_length=64)
        schema.add_field("dense_vector", DataType.FLOAT_VECTOR, dim=dense_dim)
        schema.add_field("sparse_vector", DataType.SPARSE_FLOAT_VECTOR)

        index_params = MilvusClient.prepare_index_params()
        index_params.add_index(field_name="dense_vector", index_type="AUTOINDEX", metric_type="COSINE")
        index_params.add_index(field_name="sparse_vector", index_type="SPARSE_INVERTED_INDEX", metric_type="IP")
        client.create_collection(collection_name=collection_name, schema=schema, index_params=index_params)

    @staticmethod
    def _to_milvus_row(record: dict[str, Any]) -> dict[str, Any]:
        return {
            "chunk_id": str(record.get("chunk_id", ""))[:128],
            "kb_id": str(record.get("kb_id", ""))[:128],
            "doc_id": str(record.get("doc_id", ""))[:128],
            "filename": str(record.get("filename", ""))[:512],
            "title": str(record.get("title", ""))[:512],
            "title_path": str(record.get("title_path", ""))[:1024],
            "content": str(record.get("content", ""))[:8192],
            "chunk_index": int(record.get("chunk_index") or 0),
            "subject_names": json.dumps(record.get("subject_names") or [], ensure_ascii=False)[:2048],
            "image_urls": json.dumps(record.get("image_urls") or [], ensure_ascii=False)[:4096],
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "dense_vector": record.get("dense_vector") or [],
            "sparse_vector": record.get("sparse_vector") or {},
        }


vector_write_service = VectorWriteService()
