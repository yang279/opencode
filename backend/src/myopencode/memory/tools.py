"""记忆工具：save_memory / recall_memory / list_memory / forget_memory。"""
from __future__ import annotations

from typing import Any, Dict

from ..tools.base import ToolContext, ToolResult
from .store import MemoryStore


class SaveMemoryTool:
    name = "save_memory"
    category = "memory"
    description = (
        "把一条需要长期记住的事实写入长期记忆（如用户偏好、项目约定、环境信息、重要结论）"
    )
    json_schema = {
        "type": "object",
        "properties": {
            "content": {"type": "string", "description": "要记住的事实内容"},
            "category": {"type": "string", "description": "分类：preference/convention/environment/other"},
            "importance": {"type": "integer", "description": "重要程度 1-5，默认 3"},
        },
        "required": ["content"],
    }

    def __init__(self, store: MemoryStore) -> None:
        self.store = store

    async def execute(self, args: Dict[str, Any], ctx: ToolContext) -> ToolResult:
        content = str(args.get("content", "")).strip()
        if not content:
            return ToolResult(output="save_memory 需要非空 content", error=True)
        try:
            fact = self.store.add_fact(
                content,
                category=str(args.get("category", "general")),
                importance=int(args.get("importance", 3)),
            )
        except ValueError as exc:
            return ToolResult(output=str(exc), error=True)
        return ToolResult(output="已记住: {}".format(fact.content))


class RecallMemoryTool:
    name = "recall_memory"
    category = "memory"
    description = "根据关键词检索长期记忆中的相关事实"
    json_schema = {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "检索关键词"},
        },
        "required": ["query"],
    }

    def __init__(self, store: MemoryStore) -> None:
        self.store = store

    async def execute(self, args: Dict[str, Any], ctx: ToolContext) -> ToolResult:
        query = str(args.get("query", ""))
        facts = self.store.search_facts(query, limit=10)
        for f in facts:
            self.store.mark_accessed(f.id)
        if not facts:
            return ToolResult(output="没有找到相关记忆")
        lines = ["相关记忆："]
        lines.extend("- {}".format(f.content) for f in facts)
        return ToolResult(output="\n".join(lines))


class ListMemoryTool:
    name = "list_memory"
    category = "memory"
    description = "列出长期记忆中的事实（按重要度/使用次数排序）"
    json_schema = {"type": "object", "properties": {}}

    def __init__(self, store: MemoryStore) -> None:
        self.store = store

    async def execute(self, args: Dict[str, Any], ctx: ToolContext) -> ToolResult:
        facts = self.store.list_facts(limit=50)
        if not facts:
            return ToolResult(output="暂无长期记忆")
        lines = ["长期记忆："]
        lines.extend("- [{}] {} (id: {})".format(f.category, f.content, f.id) for f in facts)
        return ToolResult(output="\n".join(lines))


class ForgetMemoryTool:
    name = "forget_memory"
    category = "memory"
    description = "按 id 删除某条长期记忆（id 通过 list_memory 获取）"
    json_schema = {
        "type": "object",
        "properties": {"id": {"type": "string", "description": "要删除的记忆 id"}},
        "required": ["id"],
    }

    def __init__(self, store: MemoryStore) -> None:
        self.store = store

    async def execute(self, args: Dict[str, Any], ctx: ToolContext) -> ToolResult:
        fact_id = str(args.get("id", ""))
        if self.store.delete_fact(fact_id):
            return ToolResult(output="已删除")
        return ToolResult(output="未找到该记忆项", error=True)