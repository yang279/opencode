"""预算护栏：按日/月累计成本，超限可硬停或仅告警。

- `record()` 由 usage 模块的 budget sink 调用，累计 + 落库
- `status()` 供 /usage/summary 与前端面板查询
- `check()` 在 LLM 调用前由 agent 调用：超限且 budget_hard_stop 时抛
  BudgetExceededError，否则仅标记告警
"""
from __future__ import annotations

from typing import Any, Dict

from ..config.schema import LLMConfig
from .usage_store import UsageStore

# 预算告警阈值（花费占预算比例）
_WARN_RATIO = 0.8


class BudgetExceededError(Exception):
    """预算超限（硬停）时抛出。"""


class BudgetGuard:
    def __init__(self, config: LLMConfig, store: UsageStore) -> None:
        self.config = config
        self.store = store

    def record(self, model: str, input_tokens: int, output_tokens: int, cost: float) -> None:
        """usage 层回调：累计成本并落库（session_id 由 usage 层透传）。"""
        self.store.record(model, None, input_tokens, output_tokens, cost)

    def status(self) -> Dict[str, Any]:
        day = self.store.total_day()
        month = self.store.total_month()
        day_cost = float(day.get("cost", 0.0))
        month_cost = float(month.get("cost", 0.0))

        day_budget = self.config.daily_budget_usd
        month_budget = self.config.monthly_budget_usd

        over = False
        warning = False
        ratios = []
        if day_budget is not None and day_budget > 0:
            r = day_cost / day_budget
            ratios.append(r)
            if r >= 1.0:
                over = True
            elif r >= _WARN_RATIO:
                warning = True
        if month_budget is not None and month_budget > 0:
            r = month_cost / month_budget
            ratios.append(r)
            if r >= 1.0:
                over = True
            elif r >= _WARN_RATIO:
                warning = True

        return {
            "daily_spent": day_cost,
            "daily_budget": day_budget,
            "monthly_spent": month_cost,
            "monthly_budget": month_budget,
            "over": over,
            "warning": warning and not over,
            "hard_stop": self.config.budget_hard_stop,
        }

    def message(self, st: Dict[str, Any]) -> str:
        if st["monthly_budget"]:
            return "已达本月预算上限 ${:.4f} / ${:.4f}".format(
                st["monthly_spent"], st["monthly_budget"]
            )
        return "已达今日预算上限 ${:.4f} / ${:.4f}".format(
            st["daily_spent"], st["daily_budget"]
        )
