"""向用户提问工具：触发人机中断，把用户的文字回答作为工具结果回填给模型。

执行被 agent 层拦截（见 agent._run_tool 的 ask_user 分支），这里仅提供 schema 与
兜底实现，避免被当成普通工具直接执行。

支持多选项问答：`options` 为一组候选（可标 recommended），`multi` 控制单选/多选。
"""
from __future__ import annotations

from typing import Any, Dict

from .base import ToolContext, ToolResult


class AskUserTool:
    name = "ask_user"
    category = "interrupt"
    description = (
        "当信息不足或需要用户确认/补充时，向用户提一个问题，等待其回答后继续。"
        "如有候选答案，通过 options 提供给用户选择（可标 recommended 推荐项，multi 设为 true 允许多选）。"
    )
    json_schema = {
        "type": "object",
        "properties": {
            "question": {"type": "string", "description": "要询问用户的问题"},
            "options": {
                "type": "array",
                "description": "候选选项列表（可选）。若提供则为选择题，用户可点选或自填。",
                "items": {
                    "type": "object",
                    "properties": {
                        "label": {"type": "string", "description": "选项文本"},
                        "description": {"type": "string", "description": "选项补充说明（可选）"},
                        "recommended": {"type": "boolean", "description": "是否推荐该选项（可选）"},
                    },
                    "required": ["label"],
                },
            },
            "multi": {"type": "boolean", "description": "是否允许多选（默认 false 单选）"},
        },
        "required": ["question"],
    }

    async def execute(self, args: Dict[str, Any], ctx: ToolContext) -> ToolResult:
        return ToolResult(output="ask_user 应被 agent 层拦截处理", error=True)