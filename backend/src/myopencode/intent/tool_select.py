"""工具识别：按意图剪枝 + 安全 gating。"""
from __future__ import annotations

from typing import Dict, List

from ..config.schema import IntentConfig
from .base import RecognitionContext
from .schema import (
    ALWAYS_GROUPS,
    CATEGORY_UNKNOWN,
    DESTRUCTIVE_GROUPS,
    INTENT_TO_TOOL_GROUPS,
    Intent,
)


class ToolRecognizer:
    def __init__(self, config: IntentConfig) -> None:
        self.config = config

    async def recognize(self, ctx: RecognitionContext, current: Intent) -> Intent:
        if not self.config.tool_enabled:
            current.tool_names = None  # 全部
            return current

        by_category: Dict[str, List[str]] = {}
        for t in ctx.tools_meta:
            name = str(t.get("name", ""))
            if not name:
                continue
            by_category.setdefault(str(t.get("category", "read")), []).append(name)

        if current.category == CATEGORY_UNKNOWN:
            current.tool_names = None  # 未知 → 全部
            return current

        groups = list(INTENT_TO_TOOL_GROUPS.get(current.category, []))
        if not self.config.gate_destructive:
            groups.extend(DESTRUCTIVE_GROUPS)
        groups.extend(ALWAYS_GROUPS)

        selected: List[str] = []
        for g in groups:
            selected.extend(by_category.get(g, []))
        current.tool_names = list(dict.fromkeys(selected))
        return current