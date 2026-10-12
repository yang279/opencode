"""工具注册表。"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from ..llm.base import ToolSchema
from .base import Tool, ToolContext
from .ask_user import AskUserTool
from .delegate_tool import DelegateTool
from .files import EditFileTool, ReadFileTool, WriteFileTool
from .plan_tool import PlanTool
from .run_code import RunCodeTool
from .search import GlobTool, GrepTool, ListDirTool
from .shell import ShellTool


def _default_tools() -> List[Tool]:
    return [
        ReadFileTool(),
        WriteFileTool(),
        EditFileTool(),
        ListDirTool(),
        GlobTool(),
        GrepTool(),
        ShellTool(),
        RunCodeTool(),
        AskUserTool(),
        PlanTool(),
        DelegateTool(),
    ]


class ToolRegistry:
    def __init__(
        self,
        tools: Optional[List[Tool]] = None,
        extra: Optional[List[Tool]] = None,
    ) -> None:
        self._tools: Dict[str, Tool] = {}
        for t in (tools if tools is not None else _default_tools()):
            self._tools[t.name] = t
        for t in extra or []:
            self._tools[t.name] = t

    def add(self, tool: Tool) -> None:
        """动态注册工具（供 MCP 连接后注入）。"""
        self._tools[tool.name] = tool

    def get(self, name: str) -> Optional[Tool]:
        return self._tools.get(name)

    def names(self) -> List[str]:
        return list(self._tools.keys())

    def meta(self) -> List[Dict[str, Any]]:
        """工具完整元信息（含 category），供意图/工具识别使用。"""
        return [
            {
                "name": t.name,
                "description": t.description,
                "category": getattr(t, "category", "read"),
            }
            for t in self._tools.values()
        ]

    def schemas(self, names: Optional[List[str]] = None) -> List[ToolSchema]:
        tools = self._tools.values()
        if names is not None:
            allowed = set(names)
            tools = [t for t in tools if t.name in allowed]
        return [
            ToolSchema(name=t.name, description=t.description, parameters=t.json_schema)
            for t in tools
        ]

    def list_meta(self) -> List[Dict[str, Any]]:
        return [
            {"name": t.name, "description": t.description}
            for t in self._tools.values()
        ]

    async def execute(self, name: str, args: dict, ctx: ToolContext):
        tool = self._tools.get(name)
        if tool is None:
            raise KeyError("未知工具: {}".format(name))
        return await tool.execute(args, ctx)