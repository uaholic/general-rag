"""
工具模块，负责提供 sse 相关的辅助能力。
"""
import json
import queue
import asyncio
from typing import Dict, Any, Optional, AsyncGenerator
from fastapi import Request

from app.shared.runtime.logger import logger


class SSEEvent:
    READY = "ready"         # 连接建立
    PROGRESS = "progress"   # 任务节点进度
    REWRITE = "rewrite"     # 问题改写结果
    DELTA = "delta"         # LLM 流式输出增量
    IMAGE = "image"         # 回答中需要展示的图片
    REFERENCES = "references"  # 引用来源
    FINAL = "final"         # 最终完整答案
    ERROR = "error"         # 错误信息
    CLOSE = "__close__"     # 关闭连接信号


# 全局 SSE 会话队列存储
# Key: session_id, Value: queue.Queue
_session_stream: Dict[str, queue.Queue] = {}

def get_sse_queue(session_id: str) -> Optional["queue.Queue"]:
    """获取指定 session 的队列"""
    return _session_stream.get(session_id)

def create_sse_queue(session_id: str) -> "queue.Queue":
    """创建并注册一个新的 SSE 队列"""
    logger.debug(f"[SSE] Creating queue for session: {session_id}")
    q = queue.Queue()
    _session_stream[session_id] = q
    return q

def remove_sse_queue(session_id: str):
    """移除指定 session 的队列"""
    logger.debug(f"[SSE] Removing queue for session: {session_id}")
    _session_stream.pop(session_id, None)

def _sse_pack(event: str, data: Dict[str, Any]) -> str:
    """打包 SSE 消息格式"""
    payload = json.dumps(data, ensure_ascii=False)
    # print(f"[SSE] Packing event: {event}, payload: {payload[:50]}...")
    return f"event: {event}\ndata: {payload}\n\n"


def format_sse_event(event: str, data: Dict[str, Any]) -> str:
    """对外暴露的 SSE 消息格式化函数。"""
    return _sse_pack(event, data)

def push_to_session(session_id: str, event: str, data: Dict[str, Any]):
    """
    通过 session_id 推送事件
    """
    stream_queue = get_sse_queue(session_id)
    if stream_queue:
        # print(f"[SSE] Pushing to session {session_id}: {event}")
        stream_queue.put({"event": event, "data": data})
    else:
        logger.warning(f"[SSE] No queue found for session {session_id} when pushing {event}")


def push_progress(
    session_id: str,
    step: str,
    label: str,
    current: int,
    total: int,
    message: str = "",
) -> None:
    """推送当前处理步骤，前端用来显示进度条和步骤文案。"""
    percent = 0 if total <= 0 else round(current / total * 100)
    push_to_session(
        session_id,
        SSEEvent.PROGRESS,
        {
            "step": step,
            "label": label,
            "current": current,
            "total": total,
            "percent": percent,
            "message": message,
        },
    )


def push_image(
    session_id: str,
    images: list[Dict[str, Any]],
    placement: str = "inline",
    message: str = "",
) -> None:
    """推送回答相关图片，前端可按 placement 决定内联或引用区展示。"""
    push_to_session(
        session_id,
        SSEEvent.IMAGE,
        {
            "placement": placement,
            "message": message,
            "images": images,
        },
    )


def push_references(session_id: str, references: list[Dict[str, Any]]) -> None:
    """推送引用来源列表。"""
    push_to_session(session_id, SSEEvent.REFERENCES, {"references": references})

async def sse_generator(session_id: str, request: Request):
    """
    SSE 生成器，用于 FastAPI 的 StreamingResponse
    """
    logger.debug(f"[SSE] Generator started for session: {session_id}")
    stream_queue = get_sse_queue(session_id)
    if stream_queue is None:
        # 如果没有对应的队列，直接结束
        logger.warning(
            f"[SSE] Queue not found for session {session_id}. "
            f"Available sessions: {list(_session_stream.keys())}"
        )
        return

    loop = asyncio.get_running_loop()
    try:
        # 发送连接建立信号
        logger.debug(f"[SSE] Sending ready signal for {session_id}")
        yield _sse_pack("ready", {})

        while True:
            # 若客户端断开，尽快退出
            if await request.is_disconnected():
                logger.debug(f"[SSE] Client disconnected: {session_id}")
                break

            try:
                # 使用 run_in_executor 避免阻塞 async 事件循环
                # {event:"process" : data: {任务状态 / 已完成节点 / 进行中节点}}
                msg = await loop.run_in_executor(None, stream_queue.get, True, 1.0)
            except queue.Empty:
                # print(f"[SSE] Queue empty for {session_id}, waiting...")
                continue

            event = msg.get("event")
            data = msg.get("data")
            
            # print(f"[SSE] Yielding event {event} for {session_id}")

            # 特殊关闭事件
            if event == "__close__":
                logger.debug(f"[SSE] Closing signal received for {session_id}")
                break

            yield _sse_pack(event, data)
    except (asyncio.CancelledError, ConnectionResetError, BrokenPipeError):
        logger.debug(f"[SSE] Client disconnected (Cancelled/Reset/Pipe): {session_id}")
        # 生成器被取消/对端断开：静默退出
        return
    except Exception as e:
        logger.exception(f"[SSE] Exception in generator for {session_id}: {e}")
    finally:
        logger.debug(f"[SSE] Generator finished for {session_id}")
        # 清理资源
        remove_sse_queue(session_id)
