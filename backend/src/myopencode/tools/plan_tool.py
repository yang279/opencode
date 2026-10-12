"""plan 工具：把任务拆解为带依赖的步骤列表。

执行被 agent 层拦截（见 agent._run_tool 的 plan 分支），这里仅提供 schema 与兜底实现。
"""
from __future__ import annotations

from typing import Any, Dict

from .base import ToolContext, ToolResult


class PlanTool:
    name = "plan"
    category = "plan"
    description = (
        "把复杂任务拆解为带依赖关系的可执行步骤列表（供后续逐步或并行执行）。"
        "适用于多步骤任务：先规划再执行。"
    )
    json_schema = {
        "type": "object",
        "properties": {
            "task": {"type": "string", "description": "要拆解的任务描述"},
        },
        "required": ["task"],
    }

    async def execute(self, args: Dict[str, Any], ctx: ToolContext) -> ToolResult:
        return ToolResult(output="plan 应被 agent 层拦截处理", error=True)
