"""文件工具：read_file / write_file / edit_file（精确字符串替换，返回 diff）。"""
from __future__ import annotations

import difflib
import os
from typing import Any, Dict

from .base import ToolContext, ToolResult


def _read(path: str) -> str:
    with open(path, "r", encoding="utf-8") as fh:
        return fh.read()


def _unified_diff(old: str, new: str, label: str) -> str:
    return "".join(
        difflib.unified_diff(
            old.splitlines(keepends=True),
            new.splitlines(keepends=True),
            fromfile=label,
            tofile=label,
        )
    )


class ReadFileTool:
    name = "read_file"
    category = "read"
    description = "读取指定文件内容"
    json_schema = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "相对于工作目录的文件路径"}
        },
        "required": ["path"],
    }

    async def execute(self, args: Dict[str, Any], ctx: ToolContext) -> ToolResult:
        path = ctx.resolve_path(args.get("path", ""))
        limit = int(getattr(ctx, "max_output_bytes", 262144))
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as fh:
                content = fh.read(limit)
                truncated = bool(fh.read(1))
        except FileNotFoundError:
            return ToolResult(output="文件不存在: {}".format(path), error=True)
        except IsADirectoryError:
            return ToolResult(output="路径是目录: {}".format(path), error=True)
        if truncated:
            content += "\n…[文件过大，已截断 {} 字节]".format(limit)
        return ToolResult(output=content)


class WriteFileTool:
    name = "write_file"
    category = "write"
    description = "创建或覆盖写入文件"
    json_schema = {
        "type": "object",
        "properties": {
            "path": {"type": "string"},
            "content": {"type": "string"},
        },
        "required": ["path", "content"],
    }

    async def execute(self, args: Dict[str, Any], ctx: ToolContext) -> ToolResult:
        path = ctx.resolve_path(args.get("path", ""), write=True)
        content = args.get("content", "")
        existed = os.path.exists(path)
        old = _read(path) if existed else ""
        if ctx.backup is not None:
            ctx.backup.before_write(path, existed)
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(content)
        diff = _unified_diff(old, content, args.get("path", path))
        return ToolResult(output="已写入 {}".format(path), diff=diff)


class EditFileTool:
    name = "edit_file"
    category = "write"
    description = "精确字符串替换编辑文件（old_string 必须唯一匹配）"
    json_schema = {
        "type": "object",
        "properties": {
            "path": {"type": "string"},
            "old_string": {"type": "string"},
            "new_string": {"type": "string"},
        },
        "required": ["path", "old_string", "new_string"],
    }

    async def execute(self, args: Dict[str, Any], ctx: ToolContext) -> ToolResult:
        path = ctx.resolve_path(args.get("path", ""), write=True)
        old = args.get("old_string", "")
        new = args.get("new_string", "")
        try:
            content = _read(path)
        except FileNotFoundError:
            return ToolResult(output="文件不存在: {}".format(path), error=True)

        count = content.count(old)
        if count == 0:
            return ToolResult(output="未找到 old_string，无修改", error=True)
        if count > 1:
            return ToolResult(
                output="old_string 匹配到 {} 处，需唯一".format(count), error=True
            )
        if ctx.backup is not None:
            ctx.backup.before_write(path, True)
        updated = content.replace(old, new, 1)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(updated)
        diff = _unified_diff(content, updated, args.get("path", path))
        return ToolResult(output="已编辑 {}".format(path), diff=diff)