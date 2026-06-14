"""文档向量写入服务。"""
from __future__ import annotations

from typing import Any

from app.infra.vectorstore.milvus_gateway import milvus_gateway


class VectorWriteService:
    """封装 Milvus 写入与删除。

    当前只放清晰接口和 TODO，不强行创建 collection。
    你后续练习时可以先确认 collection schema，再实现 upsert/delete。
    """

    def delete_document_chunks(self, doc_id: str) -> int:
        """删除某个文档旧 chunk。

        TODO: 练习点：用 Milvus filter 删除 doc_id 对应数据。
        示例方向：
            milvus_gateway.client.delete(
                collection_name=milvus_gateway.chunk_collection_name,
                filter=f'doc_id == "{doc_id}"',
            )
        """
        _ = milvus_gateway.chunk_collection_name
        _ = doc_id
        return 0

    def upsert_chunks(self, records: list[dict[str, Any]]) -> int:
        """写入 chunk 向量。

        TODO: 练习点：确认 Milvus collection 字段后，把 records 转成 insert/upsert 所需结构。
        当前返回记录数，保证导入图骨架可以先跑通。
        """
        _ = milvus_gateway.chunk_collection_name
        return len(records)


vector_write_service = VectorWriteService()
