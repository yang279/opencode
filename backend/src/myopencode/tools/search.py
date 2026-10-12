"""搜索工具：list_dir / glob / grep。"""
from __future__ import annotations

import fnmatch
import os
import re
from typing import Any, Dict, List

from .base import ToolContext, ToolResult


class ListDirTool:
    name = "list_dir"
    category = "read"
    description = "列出目录内容"
    json_schema = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "目录路径，默认工作目录"}
        },
    }

    async def execute(self, args: Dict[str, Any], ctx: ToolContext) -> ToolResult:
        path = ctx.resolve_path(args.get("path", "."))
        try:
            entries = sorted(os.listdir(path))
        except FileNotFoundError:
            return ToolResult(output="目录不存在: {}".format(path), error=True)
        lines = []
        for name in entries:
            full = os.path.join(path, name)
            suffix = "/" if os.path.isdir(full) else ""
            lines.append(name + suffix)
        return ToolResult(output="\n".join(lines))


class GlobTool:
    name = "glob"
    category = "read"
    description = "按通配符匹配文件路径"
    json_schema = {
        "type": "object",
        "properties": {
            "pattern": {"type": "string", "description": "如 **/*.py"}
        },
        "required": ["pattern"],
    }

    async def execute(self, args: Dict[str, Any], ctx: ToolContext) -> ToolResult:
        pattern = args.get("pattern", "*")
        root = ctx.working_dir
        matches: List[str] = []
        for dirpath, _dirs, files in os.walk(root):
            if ".git" in dirpath or "node_modules" in dirpath or "__pycache__" in dirpath:
                continue
            for f in files:
                rel = os.path.relpath(os.path.join(dirpath, f), root)
                if fnmatch.fnmatch(rel, pattern):
                    matches.append(rel)
        return ToolResult(output="\n".join(sorted(matches)[:500]))


class GrepTool:
    name = "grep"
    category = "read"
    description = "按正则搜索文件内容"
    json_schema = {
        "type": "object",
        "properties": {
            "pattern": {"type": "string"},
            "path": {"type": "string", "description": "搜索目录，默认工作目录"},
        },
        "required": ["pattern"],
    }

    async def execute(self, args: Dict[str, Any], ctx: ToolContext) -> ToolResult:
        pattern = args.get("pattern", "")
        base = ctx.resolve_path(args.get("path", "."))
        try:
            regex = re.compile(pattern)
        except re.error as exc:
            return ToolResult(output="正则错误: {}".format(exc), error=True)

        results = []
        for dirpath, _dirs, files in os.walk(base):
            if ".git" in dirpath or "node_modules" in dirpath or "__pycache__" in dirpath:
                continue
            for f in files:
                full = os.path.join(dirpath, f)
                try:
                    with open(full, "r", encoding="utf-8", errors="ignore") as fh:
                        for lineno, line in enumerate(fh, 1):
                            if regex.search(line):
                                rel = os.path.relpath(full, ctx.working_dir)
                                results.append("{}:{}:{}".format(rel, lineno, line.rstrip()))
                except OSError:
                    continue
                if len(results) >= 500:
                    break
        return ToolResult(output="\n".join(results) or "(无匹配)")