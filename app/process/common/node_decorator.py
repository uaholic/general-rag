"""LangGraph 节点装饰器。

节点函数只负责业务输入输出，进度结构由这里统一追加。
"""
from __future__ import annotations

from collections.abc import Callable, Mapping
from functools import wraps
from typing import Any, TypeVar, cast


StateDict = Mapping[str, Any]
NodeResult = dict[str, Any]
NodeFunc = Callable[[StateDict], NodeResult]
F = TypeVar("F", bound=NodeFunc)


def progress_event(
    *,
    step: str,
    label: str,
    current: int,
    total: int,
    message: str = "",
) -> dict[str, Any]:
    """构造前端可展示的统一进度事件。"""
    percent = 0 if total <= 0 else round(current / total * 100)
    return {
        "step": step,
        "label": label,
        "current": current,
        "total": total,
        "percent": percent,
        "message": message or label,
    }


def node_progress(
    *,
    step: str,
    label: str,
    current: int,
    total: int,
    message: str = "",
) -> Callable[[F], F]:
    """给节点返回值自动追加 progress。

    节点如果需要动态 message，可以在返回 dict 中放 `_progress_message`。
    这个内部字段会被装饰器消费，不会继续留在 state 里。
    """

    def decorator(func: F) -> F:
        @wraps(func)
        def wrapper(state: StateDict) -> NodeResult:
            result = dict(func(state) or {})
            dynamic_message = result.pop("_progress_message", "")
            progress = [
                *state.get("progress", []),
                progress_event(
                    step=step,
                    label=label,
                    current=current,
                    total=total,
                    message=dynamic_message or message,
                ),
            ]
            result["progress"] = progress
            return result

        return cast(F, wrapper)

    return decorator
