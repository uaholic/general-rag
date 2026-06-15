"""文档导入 LangGraph。"""
from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from app.process.import_.agent.nodes import (
    generate_embeddings_node,
    load_document_node,
    mark_success_node,
    parse_document_node,
    split_document_node,
    write_milvus_node,
)
from app.process.import_.agent.state import ImportGraphState
from app.process.import_.task_store import fail_import_task, finish_import_task
from app.rag.import_ import document_import_service
from app.shared.config.common import env_bool


def build_import_graph():
    graph = StateGraph(ImportGraphState)
    graph.add_node("load_document", load_document_node)
    graph.add_node("parse_document", parse_document_node)
    graph.add_node("split_document", split_document_node)
    graph.add_node("generate_embeddings", generate_embeddings_node)
    graph.add_node("write_milvus", write_milvus_node)
    graph.add_node("mark_success", mark_success_node)

    graph.add_edge(START, "load_document")
    graph.add_edge("load_document", "parse_document")
    graph.add_edge("parse_document", "split_document")
    graph.add_edge("split_document", "generate_embeddings")
    graph.add_edge("generate_embeddings", "write_milvus")
    graph.add_edge("write_milvus", "mark_success")
    graph.add_edge("mark_success", END)
    return graph.compile()


import_graph = build_import_graph()


def run_import_graph(
    doc_id: str,
    *,
    task_id: str = "",
    run_embedding: bool | None = None,
    write_milvus: bool | None = None,
    chunk_size: int = 800,
    chunk_overlap: int = 120,
) -> ImportGraphState:
    """执行导入图。"""
    if write_milvus is None:
        write_milvus = env_bool("RAG_WRITE_MILVUS", False)
    if run_embedding is None:
        run_embedding = env_bool("RAG_IMPORT_EMBEDDING", bool(write_milvus))
    if write_milvus:
        run_embedding = True

    initial_state: ImportGraphState = {
        "task_id": task_id,
        "doc_id": doc_id,
        "run_embedding": run_embedding,
        "write_milvus": write_milvus,
        "chunk_size": chunk_size,
        "chunk_overlap": chunk_overlap,
        "progress": [],
    }
    try:
        state = import_graph.invoke(initial_state)
        finish_import_task(task_id=task_id, doc_id=doc_id, state=state)
        return state
    except Exception as exc:
        document_import_service.mark_failed(doc_id=doc_id, error=str(exc))
        fail_import_task(task_id=task_id, doc_id=doc_id, error=str(exc))
        raise


__all__ = ["build_import_graph", "import_graph", "run_import_graph"]
