"""用户查询 LangGraph。"""
from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from app.process.query.agent.nodes import (
    generate_answer_node,
    load_bound_kbs_node,
    load_runtime_config_node,
    rerank_chunks_node,
    retrieve_chunks_node,
    rewrite_query_node,
    save_chat_history_node,
)
from app.process.query.agent.state import QueryGraphState


QUERY_PROGRESS_STEPS = [
    ("load_config", "读取业务线配置"),
    ("load_kb", "读取绑定知识库"),
    ("rewrite", "改写问题"),
    ("retrieve", "检索相关资料"),
    ("rerank", "整理引用来源"),
    ("generate", "生成回答"),
    ("save_history", "保存聊天记录"),
]


def build_query_graph():
    graph = StateGraph(QueryGraphState)
    graph.add_node("load_runtime_config", load_runtime_config_node)
    graph.add_node("load_bound_kbs", load_bound_kbs_node)
    graph.add_node("rewrite_query", rewrite_query_node)
    graph.add_node("retrieve_chunks", retrieve_chunks_node)
    graph.add_node("rerank_chunks", rerank_chunks_node)
    graph.add_node("generate_answer", generate_answer_node)
    graph.add_node("save_chat_history", save_chat_history_node)

    graph.add_edge(START, "load_runtime_config")
    graph.add_edge("load_runtime_config", "load_bound_kbs")
    graph.add_edge("load_bound_kbs", "rewrite_query")
    graph.add_edge("rewrite_query", "retrieve_chunks")
    graph.add_edge("retrieve_chunks", "rerank_chunks")
    graph.add_edge("rerank_chunks", "generate_answer")
    graph.add_edge("generate_answer", "save_chat_history")
    graph.add_edge("save_chat_history", END)
    return graph.compile()


query_graph = build_query_graph()


def run_query_graph(
    *,
    session_id: str,
    message: str,
    business_line_id: str,
    company_id: str = "default_company",
    use_milvus: bool = True,
    use_llm: bool = True,
) -> QueryGraphState:
    """执行查询图。"""
    initial_state: QueryGraphState = {
        "session_id": session_id,
        "company_id": company_id,
        "business_line_id": business_line_id,
        "question": message,
        "use_milvus": use_milvus,
        "use_llm": use_llm,
        "progress": [],
    }
    return query_graph.invoke(initial_state)


__all__ = ["QUERY_PROGRESS_STEPS", "build_query_graph", "query_graph", "run_query_graph"]
