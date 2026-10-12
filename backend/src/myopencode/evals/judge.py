"""evals 判定器：以规则为主，判定一次 agent 运行是否达到黄金 case 预期。"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class EvalCase:
    """黄金集单条：期望 agent 对 prompt 做出的行为。"""

    id: str
    prompt: str
    expect_tools: List[str] = field(default_factory=list)  # 期望至少调用其中一个
    expect_ask_user: bool = False
    expect_category: Optional[str] = None  # 可选：期望的意图类别


def _called_tools(events: List[Dict[str, Any]]) -> List[str]:
    out = []
    for e in events:
        if e.get("type") == "tool_call_start" and e.get("name"):
            out.append(e["name"])
        elif e.get("type") == "ask_user":
            out.append("ask_user")
    return out


def judge(case: EvalCase, events: List[Dict[str, Any]]) -> Dict[str, Any]:
    """基于事件流返回单个 case 的判定结果。"""
    reasons: List[str] = []
    tools = _called_tools(events)

    expect = set(case.expect_tools)
    if expect and not (expect & set(tools)):
        reasons.append("期望工具 {} 未调用（实际 {}）".format(sorted(expect), tools))

    if case.expect_ask_user and "ask_user" not in tools:
        reasons.append("期望 ask_user 提问但未发生")

    if case.expect_category:
        cats = [e.get("category") for e in events if e.get("type") == "intent"]
        if cats and case.expect_category not in cats:
            reasons.append("意图 {} 不匹配（实际 {}）".format(case.expect_category, cats))

    if any(e.get("type") == "error" for e in events):
        reasons.append("运行出现 error 事件")

    if not events or events[-1].get("type") != "done":
        reasons.append("未以 done 结束")

    return {
        "id": case.id,
        "passed": not reasons,
        "reasons": reasons,
        "tools": tools,
    }