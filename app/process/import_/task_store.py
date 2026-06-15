"""导入任务内存状态。

当前任务状态服务进程内保存，适合本地调试和单进程部署。
如果后续用多 worker 或任务队列，可替换为 MySQL/Redis 持久化。
"""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime
from threading import Lock
from typing import Any


_lock = Lock()
_tasks_by_id: dict[str, dict[str, Any]] = {}
_doc_to_task: dict[str, str] = {}


def start_import_task(*, task_id: str, doc_id: str) -> dict[str, Any]:
    task = {
        "task_id": task_id,
        "doc_id": doc_id,
        "status": "pending",
        "progress": [],
        "message": "等待开始解析",
        "error_msg": "",
        "started_at": datetime.now().isoformat(timespec="seconds"),
        "updated_at": datetime.now().isoformat(timespec="seconds"),
        "finished_at": "",
    }
    with _lock:
        _tasks_by_id[task_id] = task
        _doc_to_task[doc_id] = task_id
        return deepcopy(task)


def update_import_task(
    *,
    task_id: str | None,
    doc_id: str | None,
    status: str = "parsing",
    progress: list[dict[str, Any]] | None = None,
    message: str = "",
) -> None:
    if not task_id and doc_id:
        task_id = _doc_to_task.get(doc_id)
    if not task_id:
        return
    with _lock:
        task = _tasks_by_id.get(task_id)
        if not task:
            return
        task["status"] = status
        if progress is not None:
            task["progress"] = progress
            if progress:
                task["message"] = progress[-1].get("message") or progress[-1].get("label") or message
        elif message:
            task["message"] = message
        task["updated_at"] = datetime.now().isoformat(timespec="seconds")


def finish_import_task(*, task_id: str, doc_id: str, state: dict[str, Any]) -> None:
    progress = state.get("progress") or []
    with _lock:
        task = _tasks_by_id.get(task_id)
        if not task:
            return
        task["status"] = "success"
        task["progress"] = progress
        task["message"] = "解析完成"
        task["error_msg"] = ""
        task["updated_at"] = datetime.now().isoformat(timespec="seconds")
        task["finished_at"] = task["updated_at"]
        _doc_to_task[doc_id] = task_id


def fail_import_task(*, task_id: str, doc_id: str, error: str) -> None:
    with _lock:
        task = _tasks_by_id.get(task_id)
        if not task:
            return
        task["status"] = "failed"
        task["message"] = "解析失败"
        task["error_msg"] = error
        task["updated_at"] = datetime.now().isoformat(timespec="seconds")
        task["finished_at"] = task["updated_at"]
        _doc_to_task[doc_id] = task_id


def get_import_task_by_doc(doc_id: str) -> dict[str, Any] | None:
    with _lock:
        task_id = _doc_to_task.get(doc_id)
        if not task_id:
            return None
        task = _tasks_by_id.get(task_id)
        return deepcopy(task) if task else None
