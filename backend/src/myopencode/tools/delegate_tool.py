"""delegate 工具：派多个子代理并行执行互不依赖的子任务。

执行被 agent 层拦截（见 agent._run_tool 的 delegate 分支），这里仅提供 schema 与兜底实现。
"""
from __future__ import annotations

from typing import Any, Dict

from .base import ToolContext, ToolResult


class DelegateTool:
    name = "delegate"
    category = "plan"
    description = (
        "派多个子代理并行执行一组互不依赖的子任务，返回各自的结果摘要。"
        "适用于可并行的独立工作（如同时调研多个主题、并行生成多个章节草稿）。"
    )
    json_schema = {
        "type": "object",
        "properties": {
            "tasks": {
                "type": "array",
                "items": {"type": "string"},
                "description": "要并行执行的子任务描述列表",
            },
        },
        "required": ["tasks"],
    }

    async def execute(self, args: Dict[str, Any], ctx: ToolContext) -> ToolResult:
        return ToolResult(output="delegate 应被 agent 层拦截处理", error=True)