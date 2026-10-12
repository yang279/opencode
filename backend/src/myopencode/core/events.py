"""事件类型定义：前端与后端双向通信的统一结构。

所有事件为 dict（JSON 序列化），type 字段区分。这里用轻量常量 + 工厂函数
约定结构，避免引入运行时校验负担。
"""
from __future__ import annotations

from typing import Any, Dict

# ── 前端 → 后端 ─────────────────────────────────────────────
EVENT_USER_MESSAGE = "user_message"
EVENT_TOOL_APPROVAL = "tool_approval"
EVENT_CANCEL = "cancel"
EVENT_CONFIG_UPDATE = "config_update"
EVENT_RESUME = "resume"
EVENT_ASK_USER_REPLY = "ask_user_reply"
EVENT_SAFETY_REPLY = "safety_reply"

# ── 后端 → 前端 ─────────────────────────────────────────────
EVENT_ASSISTANT_TEXT = "assistant_text"
EVENT_TOOL_CALL_START = "tool_call_start"
EVENT_TOOL_CALL_END = "tool_call_end"
EVENT_APPROVAL_REQUEST = "approval_request"
EVENT_STATE_SNAPSHOT = "state_snapshot"
EVENT_INTENT = "intent"
EVENT_PLAN = "plan"
EVENT_PLAN_STEP = "plan_step"
EVENT_ERROR = "error"
EVENT_DONE = "done"
EVENT_PROGRESS = "progress"
EVENT_ASK_USER = "ask_user"
EVENT_SAFETY = "safety"
EVENT_CONTENT_FLAG = "content_flag"
EVENT_BUDGET_WARNING = "budget_warning"
EVENT_BUDGET_EXCEEDED = "budget_exceeded"
EVENT_DEGRADED = "degraded"
EVENT_REFLECTION = "reflection"


def user_message(content: str) -> Dict[str, Any]:
    return {"type": EVENT_USER_MESSAGE, "content": content}


def tool_approval(approval_id: str, decision: str) -> Dict[str, Any]:
    return {"type": EVENT_TOOL_APPROVAL, "id": approval_id, "decision": decision}


def cancel(session_id: str | None = None) -> Dict[str, Any]:
    return {"type": EVENT_CANCEL, "session_id": session_id}


def resume(session_id: str) -> Dict[str, Any]:
    return {"type": EVENT_RESUME, "session_id": session_id}


def ask_user_reply(question_id: str, answer: str) -> Dict[str, Any]:
    return {"type": EVENT_ASK_USER_REPLY, "id": question_id, "answer": answer}


def assistant_text(delta: str) -> Dict[str, Any]:
    return {"type": EVENT_ASSISTANT_TEXT, "delta": delta}


def tool_call_start(tool_id: str, name: str, args: Dict[str, Any]) -> Dict[str, Any]:
    return {"type": EVENT_TOOL_CALL_START, "id": tool_id, "name": name, "args": args}


def tool_call_end(tool_id: str, result: str, diff: Any = None) -> Dict[str, Any]:
    return {"type": EVENT_TOOL_CALL_END, "id": tool_id, "result": result, "diff": diff}


def approval_request(approval_id: str, tool: str, args: Dict[str, Any], message: str) -> Dict[str, Any]:
    return {
        "type": EVENT_APPROVAL_REQUEST,
        "id": approval_id,
        "tool": tool,
        "args": args,
        "message": message,
    }


def state_snapshot(state: Dict[str, Any]) -> Dict[str, Any]:
    return {"type": EVENT_STATE_SNAPSHOT, "state": state}


def intent(payload: Dict[str, Any]) -> Dict[str, Any]:
    ev = {"type": EVENT_INTENT}
    ev.update(payload)
    return ev


def plan(steps: Any) -> Dict[str, Any]:
    return {"type": EVENT_PLAN, "steps": steps}


def plan_step(step: Dict[str, Any], status: str) -> Dict[str, Any]:
    return {"type": EVENT_PLAN_STEP, "step": step, "status": status}


def error(message: str, code: Any = None) -> Dict[str, Any]:
    ev: Dict[str, Any] = {"type": EVENT_ERROR, "message": message}
    if code is not None:
        ev["code"] = str(code)
    return ev


def progress(stage: str, message: str) -> Dict[str, Any]:
    return {"type": EVENT_PROGRESS, "stage": stage, "message": message}


def ask_user(question_id: str, question: str, options: Any = None, multi: bool = False) -> Dict[str, Any]:
    ev: Dict[str, Any] = {"type": EVENT_ASK_USER, "id": question_id, "question": question}
    if options:
        ev["options"] = options
    if multi:
        ev["multi"] = True
    return ev


def safety(safety_id: str, reasons: Any, severity: str) -> Dict[str, Any]:
    return {
        "type": EVENT_SAFETY,
        "id": safety_id,
        "reasons": reasons,
        "severity": severity,
    }


def safety_reply(safety_id: str, decision: str) -> Dict[str, Any]:
    return {"type": EVENT_SAFETY_REPLY, "id": safety_id, "decision": decision}


def content_flag(message: str) -> Dict[str, Any]:
    return {"type": EVENT_CONTENT_FLAG, "message": message}


def budget_warning(status: Dict[str, Any]) -> Dict[str, Any]:
    ev = {"type": EVENT_BUDGET_WARNING}
    ev.update(status)
    return ev


def budget_exceeded(status: Dict[str, Any]) -> Dict[str, Any]:
    ev = {"type": EVENT_BUDGET_EXCEEDED}
    ev.update(status)
    return ev


def degraded(message: str, detail: Any = None) -> Dict[str, Any]:
    ev: Dict[str, Any] = {"type": EVENT_DEGRADED, "message": message}
    if detail is not None:
        ev["detail"] = detail
    return ev


def reflection(attempt: int, critique: str) -> Dict[str, Any]:
    return {"type": EVENT_REFLECTION, "attempt": attempt, "critique": critique}


def done() -> Dict[str, Any]:
    return {"type": EVENT_DONE}