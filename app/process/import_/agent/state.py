"""文档导入图 State。

State 里只放可序列化的数据，不放 SQLAlchemy Session、Milvus Client 这类连接对象。
节点需要外部资源时，在 rag/import_ 的 service 中临时获取。
"""
from __future__ import annotations

from typing import Any, TypedDict


class ImportGraphState(TypedDict, total=False):
    """文档导入流程状态。"""

    task_id: str
    doc_id: str
    kb_id: str
    filename: str
    file_type: str
    file_path: str

    raw_text: str
    minio_url: str
    parsed_md_path: str
    parsed_md_minio_url: str
    parsed_image_dir: str
    parser_engine: str
    image_records: list[dict[str, Any]]
    image_url_map: dict[str, str]
    markdown_image_refs: list[dict[str, Any]]
    asset_warnings: list[str]
    chunks: list[dict[str, Any]]
    embeddings: dict[str, list]
    vector_records: list[dict[str, Any]]

    run_embedding: bool
    write_milvus: bool
    chunk_size: int
    chunk_overlap: int

    parse_status: str
    chunk_count: int
    image_count: int
    error_msg: str
    progress: list[dict[str, Any]]
