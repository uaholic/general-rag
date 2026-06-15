"""文档导入图节点。

节点保持薄一点：只从 state 取值、调用 rag/import_ service、返回 state 增量。
"""
from __future__ import annotations

from app.process.common import node_progress
from app.process.import_.agent.state import ImportGraphState
from app.rag.import_ import document_import_service, embedding_service, vector_write_service


@node_progress(step="load_document", label="读取文档记录", current=1, total=7)
def load_document_node(state: ImportGraphState) -> ImportGraphState:
    document = document_import_service.load_document(state["doc_id"])
    return {**document}


@node_progress(step="parse_document", label="解析文档和图片", current=2, total=7)
def parse_document_node(state: ImportGraphState) -> ImportGraphState:
    parsed = document_import_service.parse_source(
        doc_id=state["doc_id"],
        file_path=state.get("file_path", ""),
        file_type=state.get("file_type", ""),
    )
    asset_file_path = parsed.get("parsed_md_path") or state.get("file_path", "")
    asset_file_type = "markdown" if parsed.get("parsed_md_path") else state.get("file_type", "")
    asset_report = document_import_service.inspect_markdown_assets(
        text=parsed.get("raw_text", ""),
        file_path=asset_file_path,
        file_type=asset_file_type,
    )
    message = f"解析文档和图片，解析器：{parsed.get('parser_engine', 'text')}"
    if asset_report.get("asset_warnings"):
        message = "解析文档和图片，发现图片引用请检查资源上传"
    return {
        **parsed,
        **asset_report,
        "_progress_message": message,
    }


@node_progress(step="split_document", label="切分 chunk", current=3, total=7)
def split_document_node(state: ImportGraphState) -> ImportGraphState:
    chunks = document_import_service.split_text(
        doc_id=state["doc_id"],
        kb_id=state["kb_id"],
        filename=state["filename"],
        text=state.get("raw_text", ""),
        image_url_map=state.get("image_url_map", {}),
        chunk_size=state.get("chunk_size", 800),
        chunk_overlap=state.get("chunk_overlap", 120),
    )
    return {
        "chunks": chunks,
        "chunk_count": len(chunks),
    }


@node_progress(step="recognize_subjects", label="识别主体", current=4, total=7)
def recognize_subjects_node(state: ImportGraphState) -> ImportGraphState:
    chunks = document_import_service.recognize_chunk_subjects(state.get("chunks", []))
    subject_count = len({name for chunk in chunks for name in chunk.get("subject_names", [])})
    return {
        "chunks": chunks,
        "chunk_count": len(chunks),
        "_progress_message": f"识别到 {subject_count} 个主体词",
    }


@node_progress(step="generate_embeddings", label="向量生成", current=5, total=7)
def generate_embeddings_node(state: ImportGraphState) -> ImportGraphState:
    if not state.get("run_embedding", False):
        return {
            "embeddings": {"dense": [], "sparse": []},
            "vector_records": state.get("chunks", []),
            "_progress_message": "跳过向量生成",
        }

    embeddings = embedding_service.embed_chunks(state.get("chunks", []))
    vector_records = embedding_service.attach_embeddings(state.get("chunks", []), embeddings)
    return {
        "embeddings": embeddings,
        "vector_records": vector_records,
        "_progress_message": "生成向量",
    }


@node_progress(step="write_milvus", label="写入 Milvus", current=6, total=7)
def write_milvus_node(state: ImportGraphState) -> ImportGraphState:
    if not state.get("write_milvus", False):
        return {
            "_progress_message": "跳过 Milvus 写入",
        }

    # 重新解析时要先删旧 chunk，否则同一文档会重复被检索到。
    vector_write_service.delete_document_chunks(state["doc_id"])
    inserted = vector_write_service.upsert_chunks(state.get("vector_records", []))
    return {
        "milvus_insert_count": inserted,
    }


@node_progress(step="finish", label="导入完成", current=7, total=7)
def mark_success_node(state: ImportGraphState) -> ImportGraphState:
    document = document_import_service.mark_success(
        doc_id=state["doc_id"],
        chunk_count=state.get("chunk_count", 0),
        image_count=state.get("image_count", 0),
        image_records=state.get("image_records", []),
        minio_url=state.get("minio_url", ""),
    )
    return {
        **document,
        "parse_status": "success",
    }
