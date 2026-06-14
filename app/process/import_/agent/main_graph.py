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
from app.rag.import_ import document_import_service


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
    run_embedding: bool = False,
    write_milvus: bool = False,
    chunk_size: int = 800,
    chunk_overlap: int = 120,
) -> ImportGraphState:
    """执行导入图。

    默认不跑 embedding / Milvus，避免练习阶段每次上传都加载大模型。
    需要真实入库时，把 run_embedding=True、write_milvus=True 打开。
    """
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
        return import_graph.invoke(initial_state)
    except Exception as exc:
        document_import_service.mark_failed(doc_id=doc_id, error=str(exc))
        raise


__all__ = ["build_import_graph", "import_graph", "run_import_graph"]
