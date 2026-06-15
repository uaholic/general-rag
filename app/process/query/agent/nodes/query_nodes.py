"""用户查询图节点。"""
from __future__ import annotations

from app.process.common import node_progress
from app.process.query.agent.state import QueryGraphState
from app.rag.query import (
    answer_generation_service,
    query_history_service,
    query_retrieval_service,
    query_runtime_service,
)


@node_progress(step="load_config", label="读取业务线配置", current=1, total=7)
def load_runtime_config_node(state: QueryGraphState) -> QueryGraphState:
    runtime = query_runtime_service.load_runtime(state["business_line_id"])
    return {**runtime}


@node_progress(step="load_kb", label="读取绑定知识库", current=2, total=7)
def load_bound_kbs_node(state: QueryGraphState) -> QueryGraphState:
    kb_ids = state.get("kb_ids", [])
    return {
        "kb_ids": kb_ids,
        "_progress_message": "当前业务线没有绑定可用知识库" if not kb_ids else "已读取当前业务线绑定知识库",
    }


@node_progress(step="rewrite", label="改写问题", current=3, total=7)
def rewrite_query_node(state: QueryGraphState) -> QueryGraphState:
    rewritten = query_retrieval_service.rewrite_query(
        question=state["question"],
        session_id=state.get("session_id", ""),
        business_line=state.get("business_line", {}),
        model_name=(state.get("model_config") or {}).get("llm_model_name", ""),
    )
    return {
        **rewritten,
    }


@node_progress(step="retrieve", label="检索相关资料", current=4, total=7)
def retrieve_chunks_node(state: QueryGraphState) -> QueryGraphState:
    chunks = query_retrieval_service.search(
        query=state.get("rewritten_query") or state["question"],
        kb_ids=state.get("kb_ids", []),
        top_k=state.get("top_k", 5),
        use_milvus=state.get("use_milvus", False),
    )
    return {
        "retrieved_chunks": chunks,
        "_progress_message": f"检索到 {len(chunks)} 条候选片段",
    }


@node_progress(step="rerank", label="整理引用来源", current=5, total=7)
def rerank_chunks_node(state: QueryGraphState) -> QueryGraphState:
    chunks = query_retrieval_service.rerank(
        query=state.get("rewritten_query") or state["question"],
        chunks=state.get("retrieved_chunks", []),
        top_k=state.get("top_k", 5),
        use_rerank=state.get("use_rerank", False),
    )
    return {
        "reranked_chunks": chunks,
        "references": query_retrieval_service.build_references(chunks),
        "images": query_retrieval_service.collect_images(chunks),
    }


@node_progress(step="generate", label="生成回答", current=6, total=7)
def generate_answer_node(state: QueryGraphState) -> QueryGraphState:
    answer = answer_generation_service.generate(
        question=state["question"],
        business_line=state.get("business_line", {}),
        chunks=state.get("reranked_chunks", []),
        model_name=(state.get("model_config") or {}).get("llm_model_name", ""),
        use_llm=state.get("use_llm", False),
    )
    return {
        "answer": answer,
    }


@node_progress(step="save_history", label="保存聊天记录", current=7, total=7)
def save_chat_history_node(state: QueryGraphState) -> QueryGraphState:
    query_history_service.update_user_message(state)
    query_history_service.save_assistant_message(state)
    return {}
