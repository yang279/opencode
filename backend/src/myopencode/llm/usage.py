"""Token 用量与成本统计：provider 自报，集中计费。"""
from __future__ import annotations

import contextvars
from typing import Callable, Dict, Optional

from ..core import metrics
from ..core import tracing

# model -> {"in_per_mtok": float, "out_per_mtok": float}
_pricing: Dict[str, Dict[str, float]] = {}

# 会话级 token 归因回调：(session_id, input_tokens, output_tokens) -> None
_usage_sink: Optional[Callable[[str, int, int], None]] = None

# 预算护栏回调：(session_id, model, input_tokens, output_tokens, cost) -> None
_budget_sink: Optional[Callable[[Optional[str], str, int, int, float], None]] = None

# delegate 组成本计数器：contextvar 承载，[累计成本] 列表原地累加
_delegate_cost_ctx: contextvars.ContextVar[Optional[list]] = contextvars.ContextVar(
    "delegate_cost", default=None
)


def configure(pricing: Optional[Dict[str, Dict[str, float]]]) -> None:
    global _pricing
    _pricing = dict(pricing or {})


def set_usage_sink(sink: Optional[Callable[[str, int, int], None]]) -> None:
    """注册会话级 token 归因回调（由 server 装配时注入 SessionManager.add_usage）。"""
    global _usage_sink
    _usage_sink = sink


def set_budget_sink(sink: Optional[Callable[[Optional[str], str, int, int, float], None]]) -> None:
    """注册预算累计回调（由 server 装配时注入 BudgetGuard.record）。"""
    global _budget_sink
    _budget_sink = sink


def compute_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    p = _pricing.get(model)
    if not p:
        return 0.0
    return (
        input_tokens / 1_000_000 * float(p.get("in_per_mtok", 0.0))
        + output_tokens / 1_000_000 * float(p.get("out_per_mtok", 0.0))
    )


def begin_delegate_cost():
    """开启一段 delegate 成本统计，返回结束时的 token。"""
    return _delegate_cost_ctx.set([0.0])


def end_delegate_cost(token) -> float:
    """结束统计并返回期间累计成本（美元）。"""
    counter = _delegate_cost_ctx.get()
    _delegate_cost_ctx.reset(token)
    return float(counter[0]) if counter else 0.0


def delegate_cost_active() -> bool:
    return _delegate_cost_ctx.get() is not None


def _accumulate_delegate_cost(cost: float) -> None:
    counter = _delegate_cost_ctx.get()
    if counter is not None:
        counter[0] = float(counter[0]) + float(cost)


def record_usage(model: str, input_tokens: int, output_tokens: int) -> None:
    """记录一次调用的 token 用量，并按价格表（如配置）累计成本。"""
    input_tokens = int(input_tokens or 0)
    output_tokens = int(output_tokens or 0)
    metrics.incr("llm_tokens_in_total", input_tokens, model=model)
    metrics.incr("llm_tokens_out_total", output_tokens, model=model)
    session_id = None
    if _usage_sink is not None or _budget_sink is not None:
        session_id = tracing.current().get("session_id")
    if _usage_sink is not None and session_id:
        _usage_sink(session_id, input_tokens, output_tokens)
    cost = compute_cost(model, input_tokens, output_tokens)
    if cost > 0:
        metrics.observe("llm_cost_total", cost, model=model)
    if _budget_sink is not None:
        _budget_sink(session_id, model, input_tokens, output_tokens, cost)
    _accumulate_delegate_cost(cost)
