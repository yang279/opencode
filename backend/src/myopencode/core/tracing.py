"""链路追踪：contextvars 存储 trace 上下文 + span 上下文管理器。

trace_id 从 WS 事件 → agent → LLM → 工具 → 沙箱子进程全程透传；
JsonFormatter 在格式化时读取这里的上下文，自动注入到每条日志。
"""
from __future__ import annotations

import contextvars
import logging
import threading
import time
import uuid
from contextlib import contextmanager
from typing import Any, Dict, Iterator, Optional

_trace_id: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "trace_id", default=None
)
_span_id: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "span_id", default=None
)
_session_id: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "session_id", default=None
)

# 进程内 span 环形缓冲，供诊断/本地 Trace 查看器读取
_MAX_SPANS = 2000
_span_buffer: list = []
_span_lock = threading.Lock()

_logger = logging.getLogger("myopencode.trace")


def new_trace(session_id: Optional[str] = None) -> str:
    """开启一条新 trace，返回 trace_id。"""
    tid = uuid.uuid4().hex[:16]
    _trace_id.set(tid)
    _span_id.set(uuid.uuid4().hex[:8])
    if session_id:
        _session_id.set(session_id)
    return tid


def set_session(session_id: Optional[str]) -> None:
    _session_id.set(session_id)


def current() -> Dict[str, Any]:
    return {
        "trace_id": _trace_id.get(),
        "span_id": _span_id.get(),
        "session_id": _session_id.get(),
    }


@contextmanager
def span(name: str, logger: Optional[logging.Logger] = None, **attrs: Any) -> Iterator[str]:
    """进入一个 span，退出时记录 span 日志（含耗时）+ 写入环形缓冲。

    用法：`with span("tool.call", tool="run_shell") as sid: ...`
    """
    parent = _span_id.get()
    sid = uuid.uuid4().hex[:8]
    _span_id.set(sid)
    start = time.perf_counter()
    tc = {"trace_id": _trace_id.get(), "span_id": sid, "session_id": _session_id.get()}
    try:
        yield sid
    finally:
        duration_ms = round((time.perf_counter() - start) * 1000, 2)
        _span_id.set(parent)
        lg = logger or _logger
        lg.debug(
            "span",
            extra={"span": name, "duration_ms": duration_ms, **attrs},
        )
        entry = {
            "name": name,
            "span_id": sid,
            "parent_span_id": parent,
            "trace_id": tc["trace_id"],
            "session_id": tc["session_id"],
            "started_at_ms": round(start * 1000),
            "duration_ms": duration_ms,
            "attrs": {k: v for k, v in attrs.items() if v is not None},
        }
        with _span_lock:
            _span_buffer.append(entry)
            if len(_span_buffer) > _MAX_SPANS:
                del _span_buffer[: len(_span_buffer) - _MAX_SPANS]


def snapshot_spans(session_id: Optional[str] = None, limit: int = 500) -> list:
    """返回最近 span（可选按 session 过滤），最新在前。"""
    with _span_lock:
        items = list(_span_buffer)
    if session_id:
        items = [s for s in items if s.get("session_id") == session_id]
    return list(reversed(items[-limit:]))
