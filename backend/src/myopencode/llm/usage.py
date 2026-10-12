"""Token 用量与成本统计：provider 自报，集中计费。"""
from __future__ import annotations

from typing import Callable, Dict, Optional

from ..core import metrics
from ..core import tracing

# model -> {"in_per_mtok": float, "out_per_mtok": float}
_pricing: Dict[str, Dict[str, float]] = {}

# 会话级 token 归因回调：(session_id, input_tokens, output_tokens) -> None
_usage_sink: Optional[Callable[[str, int, int], None]] = None

# 预算护栏回调：(model, input_tokens, output_tokens, cost) -> None
_budget_sink: Optional[Callable[[str, int, int, float], None]] = None


def configure(pricing: Optional[Dict[str, Dict[str, float]]]) -> None:
    global _pricing
    _pricing = dict(pricing or {})


def set_usage_sink(sink: Optional[Callable[[str, int, int], None]]) -> None:
    """注册会话级 token 归因回调（由 server 装配时注入 SessionManager.add_usage）。"""
    global _usage_sink
    _usage_sink = sink


def set_budget_sink(sink: Optional[Callable[[str, int, int, float], None]]) -> None:
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


def record_usage(model: str, input_tokens: int, output_tokens: int) -> None:
    """记录一次调用的 token 用量，并按价格表（如配置）累计成本。"""
    input_tokens = int(input_tokens or 0)
    output_tokens = int(output_tokens or 0)
    metrics.incr("llm_tokens_in_total", input_tokens, model=model)
    metrics.incr("llm_tokens_out_total", output_tokens, model=model)
    if _usage_sink is not None:
        session_id = tracing.current().get("session_id")
        if session_id:
            _usage_sink(session_id, input_tokens, output_tokens)
    cost = compute_cost(model, input_tokens, output_tokens)
    if cost > 0:
        metrics.observe("llm_cost_total", cost, model=model)
    if _budget_sink is not None:
        _budget_sink(model, input_tokens, output_tokens, cost)
