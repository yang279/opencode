"""rag_search 工具：让模型在本地知识库中主动检索（多路召回 + RRF + 重排）。"""
from __future__ import annotations

from typing import Any, Dict

from .base import ToolResult


class RagSearchTool:
    name = "rag_search"
    description = "在本地知识库中检索与查询相关的文档片段，返回最相关的内容。"
    category = "read"
    json_schema: Dict[str, Any] = {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "检索查询，尽量用具体的关键词或完整问题"},
        },
        "required": ["query"],
    }

    def __init__(self, service: Any) -> None:
        self._service = service

    async def execute(self, args: Dict[str, Any], ctx: Any) -> ToolResult:
        query = str((args or {}).get("query", "")).strip()
        if not query:
            return ToolResult(output="rag_search 需要 query 参数", error=True)
        try:
            results = await self._service.search(query)
        except Exception as exc:
            return ToolResult(output="知识库检索失败: {}".format(exc), error=True)
        if not results:
            return ToolResult(output="知识库中没有检索到相关内容。")
        lines = []
        for i, r in enumerate(results, 1):
            head = r.get("heading") or r.get("source") or ""
            lines.append("[{}] 来源: {} · 标题: {}".format(i, r.get("source", ""), head))
            lines.append(r.get("text", ""))
        return ToolResult(output="\n\n".join(lines))