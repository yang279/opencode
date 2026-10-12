"""evals 评测基座：黄金集 + 规则判定 + 运行器（离线，按需运行）。"""
from .judge import EvalCase, judge

__all__ = ["EvalCase", "judge"]