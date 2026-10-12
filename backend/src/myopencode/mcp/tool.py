"""MCP 工具包装为统一的 Tool 接口，接入现有 agent 循环与审批。"""
from __future__ import annotations

from typing import Any, Dict

from ..tools.base import ToolContext, ToolResult
from .client import MCPClient


def _extract_text(result: Dict[str, Any]) -> str:
    """MCP tools/call 结果 content 为 [{type:text,text:...}]，拼接为纯文本。"""
    content = result.get("content")
    if not isinstance(content, list):
        return str(content)
    parts = []
    for item in content:
        if isinstance(item, dict) and item.get("type") == "text":
            parts.append(str(item.get("text", "")))
        elif isinstance(item, dict):
            parts.append(str(item))
        else:
            parts.append(str(item))
    return "\n".join(parts)


class McpTool:
    def __init__(self, server: str, client: MCPClient, spec: Dict[str, Any]) -> None:
        self.server = server
        self.client = client
        self.category = "mcp"
        self._tool_name = str(spec.get("name", ""))
        self.name = "mcp_{}_{}".format(server, self._tool_name)
        self.description = str(spec.get("description", "")) or "来自 MCP server {} 的工具".format(server)
        schema = spec.get("inputSchema") if isinstance(spec.get("inputSchema"), dict) else {}
        self.json_schema = schema or {"type": "object", "properties": {}}

    async def execute(self, args: Dict[str, Any], ctx: ToolContext) -> ToolResult:
        try:
            result = await self.client.call_tool(self._tool_name, args)
        except Exception as exc:  # pragma: no cover
            return ToolResult(output="MCP 调用失败: {}".format(exc), error=True)
        is_error = bool(result.get("isError", False))
        return ToolResult(output=_extract_text(result), error=is_error)